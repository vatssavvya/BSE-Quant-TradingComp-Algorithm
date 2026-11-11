"""Daily evaluator API for seven anonymized BSE competition assets."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

ASSETS = tuple(f"Asset_{letter}" for letter in "ABCDEFG")
FIELDS = ("Open", "High", "Low", "Close", "Volume")
HISTORY = 64
FEE = 0.0005
GROSS = 0.65
HOLD = 7
MAX_CALENDAR_DAYS = 18
SELECTED = "trend_filter"
CANDIDATES = (
    "momentum_equal", "momentum_iv", "reversal_iv",
    "blend_iv", "trend_equal", "trend_iv", "trend_filter",
)


def features(closes):
    """Compute signals at the close, with identical batches suppressed causally."""
    data = closes.tail(HISTORY)
    unique = []
    for asset in ASSETS:
        if all(not np.array_equal(data[asset], data[other]) for other in unique):
            unique.append(asset)
    log_close = np.log(data[unique])
    daily = log_close.diff()
    sigma = daily.tail(20).std().clip(lower=0.005)
    medium = (log_close.iloc[-1] - log_close.iloc[-64]) / sigma
    short = log_close.iloc[-1] - log_close.iloc[-4]
    reversal = -(short - short.median()) / sigma
    market = daily.mean(axis=1).dropna()
    return medium, reversal, sigma, market


def _basket(signal, sizing, gross, long_only=False):
    w = pd.Series(0.0, index=ASSETS)
    ranked = signal.sort_values(ascending=False, kind="stable")
    if long_only:
        names = ranked[ranked > 0].index[:3]
        if len(names):
            w.loc[names] = gross * sizing[names] / sizing[names].sum()
        return w
    n = min(2, len(ranked) // 2)
    if n:
        for sign, names in ((1, ranked.index[:n]), (-1, ranked.index[-n:])):
            w.loc[names] = sign * gross / 2 * sizing[names] / sizing[names].sum()
    return w


def weights_from_features(info, variant=SELECTED):
    medium, reversal, sigma, market = info
    size = pd.Series(1.0, index=sigma.index) if variant.endswith("equal") else 1 / sigma
    if variant == "reversal_iv":
        return _basket(reversal, size, GROSS)
    if variant == "blend_iv":
        return (_basket(medium, size, GROSS) + _basket(reversal, size, GROSS)) / 2
    if variant.startswith("trend"):
        gross = GROSS
        if variant == "trend_filter" and market.tail(10).std() > 1.5 * market.std():
            gross /= 2
        return _basket(medium, size, gross, long_only=True)
    if variant in CANDIDATES:
        return _basket(medium, size, GROSS)
    raise ValueError(f"Unknown strategy {variant!r}")


@dataclass
class TradingStrategy:
    """Instantiate once per evaluation. Pass only completed closes as history.

    Call once after each completed session. execution_date is the next scheduled
    session, which may be provided without supplying any future market values.
    position is the actual currently open basket or None, based on fills.
    """
    variant: str = SELECTED
    hold_sessions: int = HOLD
    close_history: pd.DataFrame | None = None

    def on_day_close(self, daily_data, portfolio_state):
        day = pd.Timestamp(daily_data["date"]).normalize()
        close = pd.Series(
            {a: float(daily_data["assets"][a]["Close"]) for a in ASSETS},
            name=day,
        )
        if not np.isfinite(close).all() or (close <= 0).any():
            raise ValueError("Every close must be finite and positive")
        if self.close_history is not None:
            if day <= self.close_history.index[-1]:
                raise ValueError("Use strictly increasing completed session dates")
            self.close_history = pd.concat(
                [self.close_history.tail(HISTORY - 1), close.to_frame().T]
            )
        else:
            self.close_history = close.to_frame().T
        info = features(self.close_history) if len(self.close_history) >= HISTORY else None
        return decide(info, portfolio_state, self.variant, self.hold_sessions)


def decide(info, state, variant, hold_sessions):
    """Return explicit next-open instructions. An exit consumes that session."""
    position = state["position"]
    if state.get("final_session"):
        return {"action": "close" if position else "hold"}
    if position:
        elapsed = (pd.Timestamp(state["execution_date"]) -
                   pd.Timestamp(position["entry_date"])).days
        if position["sessions_held"] >= hold_sessions or elapsed >= MAX_CALENDAR_DAYS:
            return {"action": "close"}
        return {"action": "hold"}
    if info is not None:
        weights = weights_from_features(info, variant)
        if weights.abs().sum() > 0:
            return {"action": "open", "weights": weights.to_dict()}
    return {"action": "hold"}


_default = TradingStrategy()


def on_day_close(daily_data, portfolio_state):
    """Module-level entry point for a single run. Prefer a fresh class instance."""
    return _default.on_day_close(daily_data, portfolio_state)
