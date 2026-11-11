# Explain the strategy in a meeting

> I look for stocks that have been climbing over roughly three months, then ask how bumpy that climb was. I buy up to three names with the strongest positive trend relative to their recent daily volatility. The more volatile names get smaller allocations, and I use half the usual capital when the basket of available stocks has recently become unusually volatile. After seven completed sessions I sell the shares, even if the same stocks still rank highly.

## The math

Let $C_{i,t}$ be asset $i$'s last completed close. Its daily log return is $r_{i,t} = \ln(C_{i,t}/C_{i,t-1})$. A log return is close to the ordinary percentage change when the move is small. Log returns also add across days.

- **Recent volatility.** Compute the sample standard deviation of the last 20 daily log returns. Use $\sigma_i = \max(\operatorname{SD}_{20}(r_i), 0.005)$. The floor keeps an unusually quiet stock from getting an extreme rank or allocation.
- **Trend score.** Use $s_i = \ln(C_{i,t}/C_{i,t-63})/\sigma_i$. The numerator measures the overall move. The denominator discounts stocks that regularly swing more.
- **Basket risk.** For each of the last 63 days, average the daily log returns across the distinct names. Compare the sample standard deviation of the most recent 10 average returns with 1.5 times the sample standard deviation of all 63. Use gross budget $g=0.325$ if the short-window number exceeds that threshold and $g=0.65$ otherwise.
- **Sizing.** Among up to three positive names with the highest scores, set $w_i=g(1/\sigma_i)/\sum_{j\,\text{selected}}(1/\sigma_j)$. All other weights are zero. Gross exposure is the sum of the absolute weights. For this long-only basket it equals the total initially invested.
- **Exit.** Keep the number of shares fixed. After seven closes with the position open, liquidate at the next open and spend the rest of that session flat. The calendar rule can trigger an earlier exit. Holding through a price move changes the portfolio weights, even though the shares stay fixed.

## Example trade

Suppose A, C and D have positive 63-session log gains of 10%, 8% and 12%, and daily volatilities of 1%, 2% and 3%. Their scores are 10, 4 and 4. The inverse-volatility sizing numbers are 100, 50 and 33.33. If the market filter gives the usual 65% budget, the weights are approximately 35.45%, 17.73% and 11.82%.

On $10,000 of equity, A receives about $3,545.45. At a $100 entry price the simulator buys about 35.4545 shares. If it exits at $104, the A leg earns about $141.82 before costs. The entry fee is $1.77 and the exit fee is $1.84, leaving about $138.20. The other legs have their own PnL and fees. The strategy picks the weights after yesterday's close and uses today's opening prices only to compute the shares actually filled.

## Reading the results

Daily portfolio return is today's marked equity divided by yesterday's equity minus one. Equity includes cash, the market value of open shares and fees already paid. The ledger assigns both fees to each closed trade's realized PnL and assigns the entry fee to the unrealized PnL until that trade closes.

| Metric | Formula and interpretation |
|---|---|
| Sharpe | Mean daily net return divided by its sample standard deviation, multiplied by $\sqrt{252}$. It measures how much return the portfolio earned per unit of day-to-day variability, with zero assumed cash yield. |
| CAGR | $(E_T/E_0)^{252/N}-1$, where $N$ is the number of scored sessions. It expresses the same compounded gain as an annual growth rate. |
| Maximum drawdown | The largest $1-E_t/\max(E_0,E_1,\ldots,E_t)$. It measures the deepest loss from any previous equity high. |

The two-year holdout earned 4.97% after fees but fell 43.40% from its peak. It lost 31.27% during calendar 2022 and gained 26.98% in the 2023 portion through October 6. Because the strategy is long-only, market declines can affect the entire basket. The competition awards points by relative rank on each metric, so a local backtest cannot establish a leaderboard score.
