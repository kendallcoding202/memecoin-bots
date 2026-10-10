# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 0.4 days ago. Updated Oct 10 23:39 UTC. Tracking 57 tokens that passed the rug filter, out of 122 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+4.5%** | median +0.1% (range -7.7% to +18.5%) |
| Closed trades  | 2 | median 0.5 |
| Win rate       | 50% | |
| Stops hit      | 1 | |
| Max drawdown   | 10.2% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | -24.3% |
| Frank | Oct 10 14:45 | -18.6% |
| TWEETCRAFT | Oct 10 14:45 | -9.7% |
| DRMR | Oct 10 15:10 | +2.2% |
| QUBIT | Oct 10 22:25 | -9.2% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| PQC | Oct 10 14:50 | Oct 10 22:25 | -40.6% ($-40.48) | stop |
| Tschuna | Oct 10 15:00 | Oct 10 15:05 | +147.5% ($+145.13) | take profit |

## How to read this

- Only the gap between Bot One and the random column says anything about the strategy. Both trade the same tokens with the same filter, sizing and exits.
- A token can only be bought after this test first saw it, and tokens that die stay in. That's what the backtest couldn't do.
- Fills are simulated on 5-minute candles with 1% slippage each way. If a candle touched both the stop and the target, it counts as a stop.
- A week or two of results is still a small sample. Give it at least 100 closed trades before trusting it either way.
