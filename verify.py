"""Run with python verify.py /path/to/Fellows_Data.zip."""
import sys

import numpy as np
import pandas as pd

from backtest import PERIODS, build_features, load_data, simulate
from strategy import ASSETS, FEE, GROSS, HISTORY, HOLD, SELECTED, decide, features


def main(path):
    data = load_data(path)
    signals = build_features(data)
    start, end = PERIODS["validation"]
    curve, ledger = simulate(data, signals, start, end, SELECTED)
    streamed_curve, streamed_ledger = simulate(data, None, start, end, SELECTED, stream=True)
    pd.testing.assert_frame_equal(curve, streamed_curve)
    pd.testing.assert_frame_equal(ledger, streamed_ledger)
    assert np.allclose(ledger.entry_fee, FEE * abs(ledger.shares * ledger.entry_price))
    assert np.allclose(ledger.exit_fee, FEE * abs(ledger.shares * ledger.exit_price))
    assert (ledger.exit_date - ledger.entry_date).dt.days.max() < 28
    assert curve.gross_upper_bound.max() < 1
    assert (curve.gross_close > 0).sum() > 30

    i = data.index.get_loc(ledger.entry_date.iloc[0])
    closes = data.xs("Close", axis=1, level=1)
    state = {"execution_date": data.index[i], "position": None}
    causal = features(closes.iloc[:i])
    assert "Asset_G" not in causal[0]
    modified = closes.copy()
    modified.iloc[i:] *= 20
    assert decide(causal, state, SELECTED, HOLD) == decide(
        features(modified.iloc[:i]), state, SELECTED, HOLD
    )
    modified = closes.iloc[:i].copy()
    modified.loc[modified.index[-1], "Asset_G"] *= 1.01
    assert "Asset_G" in features(modified)[0]
    position = {"entry_date": "2022-01-03", "sessions_held": 2}
    assert decide(None, {"position": position, "execution_date": "2022-01-21"},
                  SELECTED, HOLD) == {"action": "close"}

    # Controlled mixed basket: A rises 10%, B falls 10%, other prices are flat.
    # Use a small mark change here to keep the gross bound conservative.
    dates = pd.bdate_range("2024-01-01", periods=HISTORY + 2)
    tiny = pd.DataFrame(10.0, index=dates, columns=data.columns)
    tiny.loc[dates[-1], ("Asset_A", "Open")] = 11.0
    tiny.loc[dates[-1], ("Asset_B", "Open")] = 9.0
    names = list(ASSETS[:4])
    trend = pd.Series([4.0, 1.0, 3.0, 2.0], index=names)
    sigma = pd.Series(0.01, index=names)
    manual = (trend, -trend, sigma, pd.Series([0.0, 0.0]))
    c, l = simulate(tiny, [manual] * len(tiny), dates[-2], dates[-1], "momentum_equal")
    expected_pnl = GROSS / 4 * (0.1 + 0.1) - FEE * (2 * GROSS)
    assert np.isclose(c.equity.iloc[-1], 1 + expected_pnl)
    assert len(l) == 4 and (l.shares < 0).sum() == 2
    print("Passed streaming parity, causal inputs, deduplication, expiration, "
          "exposure, fee reconciliation, and hand-calculated long/short PnL.")


if __name__ == "__main__":
    main(sys.argv[1])
