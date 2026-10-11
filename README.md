# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 1.2 days ago. Updated Oct 11 20:23 UTC. Tracking 81 tokens that passed the rug filter, out of 188 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+21.9%** | median -1.4% (range -15.3% to +29.5%) |
| Closed trades  | 6 | median 2 |
| Win rate       | 33% | |
| Stops hit      | 4 | |
| Max drawdown   | 11.5% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | +33.6% |
| Frank | Oct 10 14:45 | +33.5% |
| PAID | Oct 11 06:15 | -15.3% |
| SLOPCORE | Oct 11 09:15 | -9.5% |
| HIGGS | Oct 11 09:55 | +30.1% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| DRMR | Oct 10 15:10 | Oct 11 09:55 | +147.5% ($+164.34) | take profit |
| QUBIT | Oct 10 22:25 | Oct 11 09:15 | -40.6% ($-42.31) | stop |
| API | Oct 11 01:40 | Oct 11 06:10 | -40.6% ($-43.24) | stop |
| TWEETCRAFT | Oct 10 14:45 | Oct 11 01:40 | -40.6% ($-40.52) | stop |
| PQC | Oct 10 14:50 | Oct 10 22:25 | -40.6% ($-40.48) | stop |
| Tschuna | Oct 10 15:00 | Oct 10 15:05 | +147.5% ($+145.13) | take profit |

## How to read this

- Only the gap between Bot One and the random column says anything about the strategy. Both trade the same tokens with the same filter, sizing and exits.
- A token can only be bought after this test first saw it, and tokens that die stay in. That's what the backtest couldn't do.
- Fills are simulated on 5-minute candles with 1% slippage each way. If a candle touched both the stop and the target, it counts as a stop.
- A week or two of results is still a small sample. Give it at least 100 closed trades before trusting it either way.
