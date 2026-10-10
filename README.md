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
| Filter           | `python -m memebots scan`       | Runs the rug filter on the newest Solana tokens on DexScreener (or on mints you pass in) and prints what passes and why the rest were dropped.                                                                                                     |
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
python -m unittest                           # tests
```

The public Solana RPC is heavily rate limited. For the Spy, use a free endpoint from Helius or QuickNode:

```bash
export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=YOUR_KEY"
```

All thresholds are in `memebots/config.py`.

## Not done yet

- **The API calls are untested against the live services.** The DexScreener, RugCheck, and Solana RPC parsing was written against their documented responses and is covered by tests on sample data. The environment it was built in couldn't reach those services, though. Run `scan` once and check that the output looks right.
- **The whale check is off by default.** It needs a per-trade feed such as Birdeye or Helius, and none is wired up yet. The filter logic exists and is tested, and you can turn it on with `require_whale` in `config.py`.
- **There is no live trading on purpose.** Run paper trading for a couple of weeks first. Only consider real money if the scorecard holds up across many trades, not just one good day.
- **Bot Two isn't built.** See the table above.
