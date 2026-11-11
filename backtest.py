"""Reproduce the data audit, chronological study, and fill-level ledger."""
import argparse
from io import BytesIO
from itertools import combinations
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from strategy import (
    ASSETS, CANDIDATES, FEE, FIELDS, HISTORY, HOLD, SELECTED, TradingStrategy, decide, features,
)


def load_data(path):
    path = Path(path)
    frames = {}
    archive = zipfile.ZipFile(path) if path.is_file() else None
    try:
        for asset in ASSETS:
            name = asset + ".csv"
            source = archive.read(name) if archive else (path / name).read_bytes()
            data = pd.read_csv(BytesIO(source)).rename(columns={"Close/Last": "Close"})
            data["Date"] = pd.to_datetime(data["Date"], errors="raise")
            data = data.set_index("Date", verify_integrity=True).sort_index()
            data = data[list(FIELDS)].replace(r"[$,]", "", regex=True).astype(float)
            if not np.isfinite(data.to_numpy()).all() or (data <= 0).any().any():
                raise ValueError(f"Invalid OHLCV values in {name}")
            if ((data.High < data[["Open", "Low", "Close"]].max(axis=1)) |
                    (data.Low > data[["Open", "High", "Close"]].min(axis=1))).any():
                raise ValueError(f"Invalid high/low in {name}")
            if frames and not data.index.equals(next(iter(frames.values())).index):
                raise ValueError(f"Unaligned dates in {name}")
            frames[asset] = data
    finally:
        if archive:
            archive.close()
    return pd.concat(frames, axis=1)


def audit(data, out):
    duplicates = [(a, b) for a, b in combinations(ASSETS, 2) if data[a].equals(data[b])]
    close = data.xs("Close", axis=1, level=1)
    overnight = data.xs("Open", axis=1, level=1) / close.shift() - 1
    change = close.pct_change(fill_method=None)
    flags = pd.concat({"close_to_close": change.stack(), "overnight": overnight.stack()}, axis=1)
    flags.index.names = ["date", "asset"]
    flags[flags.abs().max(axis=1) >= 0.15].to_csv(out / "price_flags.csv")
    print(f"Audit: {len(data)} aligned sessions, {data.index[0].date()} to "
          f"{data.index[-1].date()}; identical OHLCV: {duplicates}")
    print(f"Largest absolute close move {change.abs().max().max():.2%}; "
          f"largest overnight gap {overnight.abs().max().max():.2%}")


def build_features(data):
    close = data.xs("Close", axis=1, level=1)
    return [None] * (HISTORY - 1) + [
        features(close.iloc[i - HISTORY + 1:i + 1]) for i in range(HISTORY - 1, len(close))
    ]


def simulate(data, signals, start, end, variant, hold=HOLD, fee=FEE, stream=False):
    dates = data.index
    op = data.xs("Open", axis=1, level=1).to_numpy()
    cl = data.xs("Close", axis=1, level=1).to_numpy()
    hi = data.xs("High", axis=1, level=1).to_numpy()
    lo = data.xs("Low", axis=1, level=1).to_numpy()
    indices = np.flatnonzero((dates >= start) & (dates <= end) &
                            (np.arange(len(dates)) >= HISTORY))
    if not len(indices):
        raise ValueError("No tradable dates in the selected period")
    cash, previous_equity = 1.0, 1.0
    shares = np.zeros(len(ASSETS))
    position = None
    entry_price = shares.copy()
    entry_fees = shares.copy()
    fills, rows = [], []
    realized_total = 0.0
    if stream:
        callback = TradingStrategy(variant, hold)
        callback.close_history = data.xs("Close", axis=1, level=1).iloc[
            indices[0] - HISTORY:indices[0] - 1
        ].copy()

    for i in indices:
        day, prices = dates[i], op[i]
        equity_open = cash + shares @ prices
        if equity_open <= 0:
            raise ValueError(f"Nonpositive opening equity on {day}")
        state = {"position": position, "execution_date": day,
                 "final_session": i == indices[-1]}
        if stream:
            order = callback.on_day_close({
                "date": dates[i - 1],
                "assets": {a: {"Close": cl[i - 1, j]} for j, a in enumerate(ASSETS)},
            }, state)
        else:
            order = decide(signals[i - 1], state, variant, hold)
        costs, realized = 0.0, 0.0
        active = bool(position)
        gross_open_before = np.abs(shares * prices).sum() / equity_open
        if gross_open_before > 1 + 1e-10:
            raise ValueError(f"Gross exposure exceeded at the opening mark on {day}")
        if order["action"] == "close":
            exit_fees = fee * np.abs(shares * prices)
            pnl = shares * (prices - entry_price) - entry_fees - exit_fees
            for j in np.flatnonzero(shares):
                fills.append((ASSETS[j], position["entry_date"], day, shares[j],
                              entry_price[j], prices[j], entry_fees[j], exit_fees[j],
                              pnl[j], position["sessions_held"]))
            realized = pnl.sum()
            realized_total += realized
            costs = exit_fees.sum()
            cash += shares @ prices - costs
            shares.fill(0)
            position = None
        elif order["action"] == "open":
            weights = np.array([order["weights"][a] for a in ASSETS])
            assert np.isfinite(weights).all() and np.abs(weights).sum() <= 1
            shares = equity_open * weights / prices
            entry_price = prices.copy()
            entry_fees = fee * np.abs(shares * prices)
            costs = entry_fees.sum()
            cash -= shares @ prices + costs
            position = {"entry_date": day, "sessions_held": 0}
            active = True

        if position:
            position["sessions_held"] += 1
        equity = cash + shares @ cl[i]
        unrealized = shares @ (cl[i] - entry_price) - (entry_fees.sum() if position else 0)
        assert np.isclose(equity, 1 + realized_total + unrealized)
        adverse = np.where(shares >= 0, lo[i], hi[i])
        lower_equity = cash + shares @ adverse
        upper_notional = np.abs(shares) @ hi[i]
        upper_gross = upper_notional / lower_equity if lower_equity > 0 else np.inf
        if equity <= 0 or upper_gross > 1 + 1e-10:
            raise ValueError(f"Equity or conservative intraday gross bound failed on {day}")
        rows.append((day, equity, equity / previous_equity - 1, costs, active,
                     realized, unrealized, np.abs(shares * cl[i]).sum() / equity,
                     upper_gross))
        previous_equity = equity

    curve = pd.DataFrame(rows, columns=[
        "date", "equity", "return", "fees", "active", "realized_pnl",
        "unrealized_pnl", "gross_close", "gross_upper_bound",
    ]).set_index("date")
    ledger = pd.DataFrame(fills, columns=[
        "asset", "entry_date", "exit_date", "shares", "entry_price", "exit_price",
        "entry_fee", "exit_fee", "net_pnl", "sessions_held",
    ])
    assert position is None
    if len(ledger):
        assert (ledger.exit_date < ledger.entry_date + pd.DateOffset(months=1)).all()
        assert ledger.sessions_held.max() <= hold
        assert np.isclose(ledger.net_pnl.sum(), curve.equity.iloc[-1] - 1)
        assert np.isclose((ledger.entry_fee + ledger.exit_fee).sum(), curve.fees.sum())
        baskets = ledger[["entry_date", "exit_date"]].drop_duplicates().sort_values("entry_date")
        assert (baskets.entry_date.iloc[1:].to_numpy() >
                baskets.exit_date.iloc[:-1].to_numpy()).all()
    return curve, ledger


def metrics(curve):
    equity = curve.equity
    daily = curve["return"]
    volatility = daily.std()
    peak = equity.cummax().clip(lower=1)
    return {"sharpe": daily.mean() / volatility * np.sqrt(252) if volatility else 0.0,
            "cagr": equity.iloc[-1] ** (252 / len(curve)) - 1,
            "max_drawdown": (1 - equity / peak).max(),
            "total_return": equity.iloc[-1] - 1,
            "sessions": len(curve), "active_days": int(curve.active.sum()),
            "days_held_at_close": int((curve.gross_close > 0).sum()),
            "max_gross_bound": curve.gross_upper_bound.max()}


PERIODS = {
    "development_early": ("2016-10-28", "2019-12-31"),
    "development_late": ("2020-01-01", "2021-10-06"),
    "validation": ("2021-10-07", "2023-10-06"),
}



def plot_validation(out):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.ticker import PercentFormatter

    curve = pd.read_csv(out / "validation_equity.csv", index_col="date", parse_dates=True)
    equity = curve.equity
    drawdown = equity / equity.cummax().clip(lower=1) - 1
    fig, (ax, dd) = plt.subplots(
        2, 1, figsize=(10, 5.8), sharex=True, layout="constrained",
        gridspec_kw={"height_ratios": [2, 1]},
    )
    ax.set_title("BSE Quant Track  |  Final chronological holdout", loc="left", weight="bold")
    ax.plot(equity, color="#195b82", linewidth=1.7, label="Strategy after fees")
    ax.axhline(1, color="#65778a", linestyle="--", linewidth=1, label="Starting equity")
    ax.set_ylabel("Normalized equity")
    ax.legend(loc="lower right", frameon=False)
    dd.fill_between(drawdown.index, drawdown.to_numpy(), 0, color="#a54638", alpha=0.6)
    dd.set_ylabel("Drawdown")
    dd.yaxis.set_major_formatter(PercentFormatter(1))
    dd.set_xlabel("Trading date  |  October 2021 to October 2023")
    for axis in (ax, dd):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.22)
    fig.savefig(out / "validation_equity.png", dpi=180)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", help="Fellows_Data.zip or directory with seven CSVs")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--phase", choices=("development", "validation", "all"), default="all")
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    data = load_data(args.data)
    audit(data, out)
    signals = build_features(data)
    rows = []
    for label, (start, end) in PERIODS.items():
        phase = "validation" if label == "validation" else "development"
        if args.phase not in (phase, "all"):
            continue
        variants = (SELECTED,) if phase == "validation" else CANDIDATES
        for variant in variants:
            curve, ledger = simulate(data, signals, start, end, variant)
            rows.append({"period": label, "strategy": variant, **metrics(curve)})
            if variant == SELECTED:
                curve.to_csv(out / f"{label}_equity.csv")
                ledger.to_csv(out / f"{label}_trades.csv")
    if args.phase in ("development", "all"):
        checks = []
        for label, (start, end) in list(PERIODS.items())[:2]:
            for variant in ("trend_iv", "trend_filter", "blend_iv"):
                for hold, fee in ((5, FEE), (9, FEE), (HOLD, 2 * FEE)):
                    curve, _ = simulate(data, signals, start, end, variant, hold, fee)
                    checks.append({"period": label, "strategy": variant, "hold": hold,
                                   "fee_per_side": fee, **metrics(curve)})
        pd.DataFrame(checks).to_csv(out / "development_sensitivity.csv", index=False)
    if args.phase in ("validation", "all"):
        plot_validation(out)
    results = pd.DataFrame(rows)
    results.to_csv(out / f"{args.phase}_metrics.csv", index=False)
    print(results.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
