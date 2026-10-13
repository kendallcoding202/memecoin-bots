# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 2.9 days ago. Updated Oct 13 11:55 UTC. Tracking 107 tokens that passed the rug filter, out of 278 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+5.3%** | median -8.6% (range -23.5% to +5.6%) |
| Closed trades  | 8 | median 4 |
| Win rate       | 25% | |
| Stops hit      | 6 | |
| Max drawdown   | 19.1% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | +17.1% |
| Frank | Oct 10 14:45 | +5.7% |
| PAID | Oct 11 06:15 | -9.6% |
| HIGGS | Oct 11 09:55 | -8.4% |
| JEANPHIL | Oct 12 15:35 | -5.0% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| DOPE | Oct 12 13:45 | Oct 12 15:25 | -40.6% ($-46.34) | stop |
| SLOPCORE | Oct 11 09:15 | Oct 12 13:40 | -40.6% ($-41.09) | stop |
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
