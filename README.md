# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 3.6 days ago. Updated Oct 14 05:03 UTC. Tracking 121 tokens that passed the rug filter, out of 320 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+4.9%** | median -10.3% (range -27.3% to +32.1%) |
| Closed trades  | 12 | median 5.5 |
| Win rate       | 25% | |
| Stops hit      | 9 | |
| Max drawdown   | 20.5% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | +5.2% |
| PAID | Oct 11 06:15 | -11.2% |
| JEANPHIL | Oct 12 15:35 | -3.4% |
| REA | Oct 14 00:50 | +1.8% |
| DOPE | Oct 14 02:55 | -15.3% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| Frank | Oct 10 14:45 | Oct 14 02:50 | -40.6% ($-40.56) | stop |
| HUMPH | Oct 13 23:30 | Oct 14 00:50 | -40.6% ($-45.16) | stop |
| VEIL | Oct 13 15:45 | Oct 13 23:25 | +147.5% ($+150.94) | take profit |
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
