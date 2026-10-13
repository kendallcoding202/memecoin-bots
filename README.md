# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 3.2 days ago. Updated Oct 13 19:22 UTC. Tracking 112 tokens that passed the rug filter, out of 296 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+5.6%** | median -10.9% (range -30.1% to +4.2%) |
| Closed trades  | 9 | median 5 |
| Win rate       | 22% | |
| Stops hit      | 7 | |
| Max drawdown   | 19.6% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | +6.2% |
| Frank | Oct 10 14:45 | +6.6% |
| PAID | Oct 11 06:15 | -8.1% |
| JEANPHIL | Oct 12 15:35 | +8.6% |
| VEIL | Oct 13 15:45 | +33.4% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| HIGGS | Oct 11 09:55 | Oct 13 15:45 | -40.6% ($-47.34) | stop |
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
