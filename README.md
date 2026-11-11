# BSE Quant Track trading strategy

Python 3.10 or newer. Keep the original `Fellows_Data.zip` beside this directory or pass its path. The supplied market data are distributed separately.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python backtest.py /path/to/Fellows_Data.zip --phase all
python verify.py /path/to/Fellows_Data.zip
```

The backtester accepts the ZIP directly or a directory containing the seven original CSVs. It recreates the metric table, sensitivity grid, trade ledgers, daily equity and drawdown chart under `results/`. Use `--phase development` for the candidate comparison or `--phase validation` for the frozen holdout run. A fresh portfolio starts at 1.0 for each split. The first development period starts trading after 64 completed observations. Each split uses all available earlier closes as warm-up and liquidates at its last open.

Submit `strategy.py` and `STRATEGY.md`. `EXPLAINER.md` is a meeting reference. NumPy and pandas are the only evaluator dependencies.

## Evaluator contract

Create a fresh `TradingStrategy()` for each evaluation. Stream the supplied public history into the instance before the first hidden trade, or pass a date-indexed public close panel with columns `Asset_A` through `Asset_G` as `close_history`. When preloading history, stream the final public row only if it was excluded from the preload. Call the strategy exactly once per completed session and discard orders during warm-up. The final public close can generate the first hidden order.

```python
from strategy import ASSETS, TradingStrategy

strategy = TradingStrategy()
daily_data = {
    "date": "2023-10-06",
    "assets": {asset: {"Close": price} for asset, price in zip(ASSETS, closes)},
}
portfolio_state = {
    "execution_date": "2023-10-09",
    "position": None,
    "final_session": False,
}
order = strategy.on_day_close(daily_data, portfolio_state)
```

Here `closes` contains the seven closes supplied by the evaluator. Date values are ISO dates or pandas timestamps. Use the exchange calendar for `execution_date`. Market prices from the next session are unnecessary for the decision. The adapter handles fills as follows.

| Returned action | Evaluator behavior |
|---|---|
| `open` | At the scheduled open, size each signed share quantity as pre-fee equity × weight ÷ open price. Debit a fee of 0.0005 × absolute opening notional for every leg. |
| `hold` | Keep the existing share quantities. With a flat book, keep cash. |
| `close` | Close all actual shares at the next open. Debit 0.0005 × absolute closing notional for every leg. Stay flat for the rest of that session. |

After an entry, pass the actual `position={"entry_date": fill_date, "sessions_held": n}` into the callback. `n` counts completed sessions with the basket held at the close, including its entry session. Reset `position` to `None` after the exit fills. Use the optional `final_session=True` to close at the final available open and prevent entries that cannot be completed. If exit fills are delayed, retain the original entry date and keep sending the close request when due.

The supplied module also exports `on_day_close(daily_data, portfolio_state)` for a single evaluation process. The class API is preferred for repeat runs. A platform that only accepts daily weights must translate actions into fills and retain shares across `hold`; applying the same weights every day would rebalance the strategy and change fees and returns.

Confirm with Bryan Qi that overnight exits execute at the next open, that the adapter will honor fixed shares, how dividends and price adjustments are treated for overnight holds, whether Asset_G is intentionally identical to Asset_B, and how the last evaluation session is handled. The local model uses supplied prices, fractional shares, zero cash yield and the specified fees. It has no separate dividend, borrow, financing, or spread adjustment. The official cutoff was unconfirmed.
