# memecoin-bots

Paper-trading versions of the three-bot setup from [@0xboan's post](https://x.com/0xboan/status/2108628680171815259), plus the rug filter from the same thread. The code uses real market data but only fake money. It never holds a wallet key or places a real order.

## What the post claims

|                    | Bot One: Gambler | Bot Two: House              | Bot Three: Spy                     |
| ------------------ | ---------------- | --------------------------- | ---------------------------------- |
| Edge               | reads direction  | needs volume, not direction | copies proven wallets              |
| Starting capital   | 0.25 ETH         | $0                          | $1,000                             |
| Window             | 24h              | 18h                         | 24h                                |
| Result             | 1.1 ETH net      | 1.09 ETH                    | $10,867                            |
| Can lose big?      | yes              | rarely                      | only if it copies the wrong wallet |
| Known issue        | none yet         | none yet                    | late-flag bug, fix in progress     |

The thread also describes a filter every token has to pass before a bot buys it:

- liquidity locked for at least a couple of months
- deep enough liquidity (most pairs get dropped)
- whales loading in with 200–300 SOL buys

The thread also has a lesson about position sizing. Most of the profit came from many small closes. The big wins were only big because each one was sized off the stack those small wins had built. All 33 stops were at least 10x smaller than the smallest big win.

### Read this before trusting any of it

- **None of those numbers are verified.** Results like 10x in a day, an 85% win rate, or $61 to $7,392 are screenshots of the author's best runs. Posts like this are often marketing for a paid bot or a signal group.
- **Paper results flatter you.** Real memecoin fills run into slippage, priority fees, MEV sandwich bots, and tokens that go to zero between two price checks. The paper portfolio charges 1% each way to soften this, but that is still optimistic.
- **Copy trading has a built-in problem.** You always buy after the wallet you copy, so you pay more than it did. If enough people copy a wallet, its owner can dump on them.

## What's here

| Bot              | Command                         | What it does                                                                                                                                                                                                                                          |
| ---------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backtest         | `python -m memebots backtest`   | Replays the last few days of 5-minute candles (from GeckoTerminal) through Bot One, then runs random entries on the same tokens with the same filter and stops. The gap between the two is what the strategy itself adds. |
| Spy backtest     | `python -m memebots backtest-spy` | Picks "proven" wallets from the first half of the last ~24h of $500+ trades, copies them on the second half (instantly and 30s late), and compares that to copying random active wallets. |
| Filter           | `python -m memebots scan`       | Runs the rug filter on the newest Solana tokens on DexScreener (or on mints you pass in) and prints what passes and why the rest were dropped. Besides the post's lock and liquidity rules, it rejects tokens where the top 10 wallets hold over 30%, one wallet holds over 10%, or RugCheck raises a danger flag. |
| One: Gambler     | `python -m memebots gambler`    | Buys filtered tokens that are up 5–60% in the last hour with $20k+ volume. Exits at an 8% stop or an 80% target.                                                                                                                                     |
| Two: House       | not built                       | The post never says how this bot makes money. With $0 starting capital, it most likely collects fees on other people's trading, such as a launchpad's creator-fee share or a trading bot's referral fees. Once the mechanism is pinned down, it can be added. |
| Three: Spy       | `python -m memebots spy`        | Watches the wallets in `wallets.txt` over Solana RPC. It copies their buys that pass the filter and sells when they sell.                                                                                                                         |

The Spy has a guard for the post's "late-flag bug". It skips a buy signal that is more than 60s old, or one where the price is already 15% or more above the wallet's own fill. It also reads at `confirmed` commitment instead of the RPC's default `finalized`, which saves about 13 seconds.

Every bot sizes each position at 10% of current equity, so wins grow later positions the same way the post describes. Press Ctrl-C to stop a bot. It then prints a scorecard: return, win rate, stops, biggest win, worst loss, and max drawdown. Every open and close is also logged to `runs/<bot>.jsonl`.

## Running it

Requires Python 3.10+. There are no dependencies.

```bash
python -m memebots scan                      # filter the newest tokens
python -m memebots scan <mint> <mint>        # or specific ones
python -m memebots gambler                   # paper-trade Bot One
cp wallets.example.txt wallets.txt           # add wallets to copy, one per line
python -m memebots spy                       # paper-trade Bot Three
python -m memebots backtest --stop 0.25 --target 1.0   # backtest Bot One
python -m memebots backtest-spy             # backtest Bot Three
python -m unittest                           # tests
```

The public Solana RPC is heavily rate limited. For the Spy, use a free endpoint from Helius or QuickNode:

```bash
export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=YOUR_KEY"
```

All thresholds are in `memebots/config.py`.

## Backtest results (Oct 7–10, 2026)

`python -m memebots backtest --days 3 --pools 60`: 60 SOL pools between 6 hours and 30 days old, 22 of which passed the rug filter. Every row starts with $1,000. "Random" uses the same tokens, filter, sizing and stops, with random entry times (20 runs).

| Stop | Target | Bot One entry   | Bot One return | Trades | Win rate | Random median (range) |
| ---- | ------ | --------------- | -------------- | ------ | -------- | --------------------- |
| 8%   | 80%    | up 5–60% in 1h  | **-42.5%**     | 151    | 8%       | +5% (-27 to +55)      |
| 15%  | 80%    | up 5–60% in 1h  | -40.2%         | 86     | 15%      | +17% (-23 to +62)     |
| 25%  | 100%   | up 5–60% in 1h  | -1.5%          | 45     | 24%      | +30% (-20 to +114)    |
| 40%  | 150%   | up 5–60% in 1h  | +13.7%         | 17     | 35%      | +28% (-12 to +68)     |
| 40%  | 150%   | flat (0–5%)     | +32.6%         | 12     | 50%      | +30% (-3 to +80)      |

What this says:

- **Bot One's momentum entry did worse than random entries at every stop size.** Buying something that's already up 5–60% in the hour mostly means buying near a local top.
- **An 8% stop is far too tight for memecoins.** Ordinary 5-minute swings hit it constantly (138 of the 151 trades were stopped out).
- **Don't read the positive numbers as an edge.** The tokens are ones that are still trending today, so they mostly went up over the window, and random buys made money too. Only the gap between Bot One and random counts, and it's negative or zero everywhere.
- **Three days and 22 tokens is a small sample.** Treat this as a reason to rethink the entry rule, not as a final verdict.

These rows predate the holder check. With it, 19 tokens pass and Bot One still trails random: -39.8% against a +5.5% median with the 8% stop, and +12.4% against +25.9% with a 25% stop and 100% target.

## Spy backtest results (Oct 9–10, 2026)

`python -m memebots backtest-spy`: 60 pools and 13,339 trades of $500+. Wallets were picked on Oct 9 04:40–16:41 and tested on Oct 9 16:41 to Oct 10 04:43. 125 wallets made 3 or more buys that could be scored. 20 of them counted as proven: the price an hour after their buys was up on average, and up at least half the time. The test then copied those 20 wallets on the following 12 hours, which they weren't picked on.

| Stop | Target | Instant copy (best case) | 30s late (realistic) | 20 random wallets, median (range) |
| ---- | ------ | ------------------------ | -------------------- | --------------------------------- |
| 8%   | 80%    | -4.6%                    | **-15.4%**           | -4.1% (-20 to +7)                 |
| 25%  | 100%   | +2.7%                    | -11.2%               | -6.0% (-21 to +10)                |
| 40%  | 150%   | -6.6%                    | -10.5%               | -3.6% (-12 to +5)                 |

What this says:

- **Wallets that looked smart for 12 hours didn't stay smart.** Copying them with a realistic delay did worse than copying random active wallets at every setting. A handful of good buys is mostly luck.
- **Even perfect, zero-delay copying only broke even.** That's the best case, and no real bot gets it.
- **Being late is expensive.** The gap between instant and 30s-late copying was 4 to 14 points, which is the post's "late-flag bug" in numbers. The realistic run fills at the close of the 5-minute candle, so it overstates the delay for a fast bot. The truth sits somewhere between the two columns.
- **The sample is small.** It covers 12 hours of testing, only trades of $500 or more (smaller sells are invisible), and only these 60 tokens. GeckoTerminal's free feed goes back about 24 hours. A longer test needs a paid data source or a few days of collecting trades.

## Not done yet

- **Parsing is checked against live data, but only spot-checked.** DexScreener, RugCheck and Solana RPC responses were all confirmed on real data. Free endpoints rate-limit, and calls back off and retry when that happens.
- **The LP-lock check passes nearly every pump.fun token.** Tokens that graduate from pump.fun get 100% burned LP automatically, which is why the holder check was added. The backtests can only use today's RugCheck data, not what the token looked like at the time.
- **The whale check is off by default.** It needs a per-trade feed such as Birdeye or Helius, and none is wired up yet. The filter logic exists and is tested, and you can turn it on with `require_whale` in `config.py`.
- **There is no live trading on purpose.** Run paper trading for a couple of weeks first. Only consider real money if the scorecard holds up across many trades, not just one good day.
- **Bot Two isn't built.** See the table above.
