# Volatility-scaled relative trend

Savya Vats · UCLA Bruin Software Engineers Quant Track · November 2026

I test whether stocks with the strongest recent gains per unit of daily volatility continue to outperform over roughly a week. I use relative trend to select stocks, inverse volatility to size them, and recent broad-market volatility to adjust how much cash I commit. All signals use only the competition’s anonymized close history.

## Trading rules

At a completed close, I rank assets by their 63-session log price change divided by the standard deviation of their last 20 daily log returns, with a 0.5% daily volatility floor. I buy up to the three strongest positive names at the next open and split the allocation in proportion to inverse volatility. Initial gross exposure is 65% of equity. It falls to 32.5% if the last 10 sessions’ volatility of the equal-weight average stock log return exceeds 1.5 times its 63-session volatility. I count exact duplicate close histories once over the 64-close signal window and keep the first alphabetical label.

I hold fixed shares for seven completed sessions and liquidate at the following open. If the scheduled execution date is at least 18 calendar days from entry, I order a full exit at that open even if seven sessions have yet to pass. Every exit is a real liquidation, with the rest of that session flat and any new position opened on a later session. Fees are 0.05% of actual notional on each side. The entry allocation leaves positive cash, so this long-only strategy stays below 100% gross while prices and cash are positive.

## Chronological results

| Period | Sharpe | CAGR | Maximum drawdown | Total return |
|---|---:|---:|---:|---:|
| Development through Dec 2019, after warm-up | 0.650 | 6.75% | 23.17% | 20.96% |
| Development Jan 2020–Oct 6, 2021 | 1.457 | 36.15% | 17.09% | 72.44% |
| Frozen holdout Oct 7, 2021–Oct 6, 2023 | 0.222 | 2.46% | 43.40% | 4.97% |

I compared seven candidates during development using the same position lifecycle and fees. The filtered strategy had the highest Sharpe and CAGR in the later development split and a smaller drawdown than the other long-only candidates there. Unfiltered inverse-volatility trend led it in the early split. The filtered version remained profitable in both development splits at 5-, 7- and 9-session holding periods and when fees doubled at seven sessions. The 50/50 momentum–reversal blend had lower drawdowns in the main comparison but lost money in the later development split at both alternate holding periods. I retained the seven-session filtered strategy before opening the final holdout.

The holdout had 395 sessions with exposure at close, 57 basket entries and a maximum holding period of 12 calendar days. The drawdown ran from January 4 to October 24, 2022, and highlights how much downside this long-only rule retains. The volatility filter sets entry size and cannot protect an existing basket from overnight gaps. A long cash-heavy period is also possible when few names show positive trends.

All seven files have 1,746 aligned, unique dates with complete, positive data and valid OHLC ranges. Asset_B and Asset_G are byte-identical. I flagged close changes or overnight gaps of at least 15%; the largest were 26.39% and 24.53% in absolute value. I retained the published prices because the large moves cannot be reliably classified from anonymous OHLCV alone. The supplied data do not establish the treatment of overnight corporate actions. The local execution model uses the Discord multi-day clarification and assumes next-open fills on entry and exit.
