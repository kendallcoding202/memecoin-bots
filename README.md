# Bot One forward paper test

Fake $1,000. Buys tokens up 5–60% in the last hour with $20,000+ volume, 10% of equity per trade, at most 5 open. Exits at a 40% stop or a 150% target.

Started Oct 10 14:42 UTC, 0.2 days ago. Updated Oct 10 20:10 UTC. Tracking 53 tokens that passed the rug filter, out of 107 seen.

|                | Bot One | Random entries, same tokens and rules |
| -------------- | ------- | ------------------------------------- |
| Return         | **+10.3%** | median +0.0% (range -4.1% to +15.7%) |
| Closed trades  | 1 | median 0 |
| Win rate       | 100% | |
| Stops hit      | 0 | |
| Max drawdown   | 6.1% | |
| Open positions | 5 | |

## Open positions

| Token | Bought (UTC) | P&L |
| ----- | ------------ | --- |
| SI276 | Oct 10 14:45 | -31.1% |
| Frank | Oct 10 14:45 | +6.6% |
| TWEETCRAFT | Oct 10 14:45 | -6.5% |
| PQC | Oct 10 14:50 | -20.9% |
| DRMR | Oct 10 15:10 | +8.8% |

## Last 20 closed trades

| Token | Bought (UTC) | Sold (UTC) | P&L | Why |
| ----- | ------------ | ---------- | --- | --- |
| Tschuna | Oct 10 15:00 | Oct 10 15:05 | +147.5% ($+145.13) | take profit |

## How to read this

- Only the gap between Bot One and the random column says anything about the strategy. Both trade the same tokens with the same filter, sizing and exits.
- A token can only be bought after this test first saw it, and tokens that die stay in. That's what the backtest couldn't do.
- Fills are simulated on 5-minute candles with 1% slippage each way. If a candle touched both the stop and the target, it counts as a stop.
- A week or two of results is still a small sample. Give it at least 100 closed trades before trusting it either way.
