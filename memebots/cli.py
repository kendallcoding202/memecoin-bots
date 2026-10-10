"""Command line: python -m memebots scan | gambler | spy"""

import argparse
import time
from datetime import datetime

from . import solana_rpc, sources
from .config import FilterConfig, RiskConfig
from .filter import check
from .gambler import Gambler
from .portfolio import PaperPortfolio
from .spy import Spy


def say(msg: str):
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


def fetch(mints: list[str], filter_cfg: FilterConfig) -> dict:
    snaps = sources.snapshots(mints)
    sources.add_lp_locks(snaps.values(), filter_cfg.min_liquidity_usd)
    return snaps


def run(interval: float, portfolio: PaperPortfolio, tick):
    """Call tick() every `interval` seconds until Ctrl-C, then print the scorecard."""
    try:
        while True:
            try:
                tick()
            except (OSError, RuntimeError, ValueError) as e:
                say(f"data error, retrying next tick: {e}")
            say(f"equity ${portfolio.equity():,.2f}, {len(portfolio.positions)} open")
            time.sleep(interval)
    except KeyboardInterrupt:
        print()
        for key, value in portfolio.stats().items():
            print(f"{key:>18}: {value}")


def cmd_scan(args, filter_cfg):
    mints = args.mints or sources.latest_solana_mints()
    snaps = fetch(mints, filter_cfg)
    passed = 0
    for snap in snaps.values():
        verdict = check(snap, filter_cfg)
        passed += verdict.passed
        status = "PASS" if verdict.passed else "drop"
        print(f"{status}  {snap.symbol[:10]:<10} {snap.mint}  {'; '.join(verdict.reasons)}")
    print(f"\n{passed} of {len(snaps)} passed ({len(mints) - len(snaps)} had no pair on DexScreener)")


def cmd_gambler(args, filter_cfg):
    portfolio = PaperPortfolio(RiskConfig(), log_path=args.log)
    bot = Gambler(portfolio, filter_cfg)

    def tick():
        mints = list(args.mints or sources.latest_solana_mints())
        mints += [m for m in portfolio.positions if m not in mints]
        now = time.time()
        for snap in fetch(mints, filter_cfg).values():
            if line := bot.on_snapshot(snap, now):
                say(line)

    say(f"Gambler paper trading ${portfolio.cash:,.0f}. Ctrl-C to stop.")
    run(args.interval, portfolio, tick)


def cmd_spy(args, filter_cfg):
    with open(args.wallets) as f:
        wallets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if not wallets:
        raise SystemExit(f"No wallets in {args.wallets}")
    portfolio = PaperPortfolio(RiskConfig(), log_path=args.log)
    bot = Spy(portfolio, filter_cfg)
    # Start from each wallet's latest transaction so we only copy trades made from now on.
    last_seen = {w: solana_rpc.latest_signature(w) for w in wallets}

    def tick():
        for wallet in wallets:
            for sig in solana_rpc.new_signatures(wallet, until=last_seen[wallet]):
                trade = solana_rpc.fetch_trade(sig, wallet)
                if trade:
                    token = fetch([trade.mint], filter_cfg).get(trade.mint)
                    say(bot.on_wallet_trade(trade, token, time.time()))
                last_seen[wallet] = sig
        if portfolio.positions:
            now = time.time()
            for snap in sources.snapshots(list(portfolio.positions)).values():
                if line := bot.on_snapshot(snap, now):
                    say(line)

    say(f"Spy watching {len(wallets)} wallets, paper trading ${portfolio.cash:,.0f}. Ctrl-C to stop.")
    run(args.interval, portfolio, tick)


def cmd_backtest(args, filter_cfg):
    from . import backtest, history

    print(f"Loading {args.days:g} days of 5-minute candles for up to {args.pools} pools...")
    histories = history.load(args.days, args.pools, args.cache)
    if not histories:
        raise SystemExit("No pools with candle data.")

    if args.no_lock_check:
        print("Skipping the LP-lock check (--no-lock-check): every token counts as locked.")
        locks = {h.mint: (100.0, float("inf")) for h in histories}
    else:
        locks = {}
        for h in histories:
            if h.liquidity_usd >= filter_cfg.min_liquidity_usd:
                locks[h.mint] = sources.lp_lock(h.mint)
        if all(lock == (None, None) for lock in locks.values()):
            print("Warning: no LP-lock data (is api.rugcheck.xyz reachable?), so the filter will reject everything.")

    bot = Gambler(PaperPortfolio(RiskConfig()), filter_cfg)
    result = backtest.replay(histories, locks, bot.wants_entry)
    start = min(h.candles[0].ts for h in histories)
    end = max(h.candles[-1].ts for h in histories)
    print(f"\n{len(histories)} pools, {datetime.fromtimestamp(start):%b %d %H:%M} to {datetime.fromtimestamp(end):%b %d %H:%M}")
    passing = sum(backtest.passes_filter(h, locks.get(h.mint, (None, None)), filter_cfg) for h in histories)
    print(f"{passing} of them pass the rug filter\n")

    print("Gambler (Bot One):")
    for trade in result.closed:
        print(f"  {datetime.fromtimestamp(trade.opened_at):%b %d %H:%M}  {trade}")
    for key, value in result.stats().items():
        print(f"  {key:>18}: {value}")

    baseline = backtest.random_baseline(histories, locks, len(result.closed), filter_cfg)
    if baseline:
        print("\nRandom entries, same tokens/filter/sizing/stops:")
        for key, value in backtest.summarize(baseline).items():
            print(f"  {key:>18}: {value}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="memebots", description="Paper-trading memecoin bots.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="run the rug filter and print what passes")
    scan.add_argument("mints", nargs="*", help="token mints (default: newest Solana tokens on DexScreener)")

    gambler = sub.add_parser("gambler", help="Bot One: paper-trade momentum on filtered tokens")
    gambler.add_argument("mints", nargs="*", help="token mints to watch (default: newest on DexScreener)")
    gambler.add_argument("--interval", type=float, default=30, help="seconds between checks")
    gambler.add_argument("--log", default="runs/gambler.jsonl")

    spy = sub.add_parser("spy", help="Bot Three: paper-copy buys from the wallets you list")
    spy.add_argument("--wallets", default="wallets.txt", help="file with one wallet address per line")
    spy.add_argument("--interval", type=float, default=15, help="seconds between checks")
    spy.add_argument("--log", default="runs/spy.jsonl")

    bt = sub.add_parser("backtest", help="replay recent history through Bot One, against random entries")
    bt.add_argument("--days", type=float, default=3, help="how much history to replay")
    bt.add_argument("--pools", type=int, default=60, help="how many recent pools to test on")
    bt.add_argument("--cache", default="runs/history.json", help="saved candles; delete to refetch")
    bt.add_argument("--no-lock-check", action="store_true", help="treat every token as LP-locked")

    args = parser.parse_args(argv)
    commands = {"scan": cmd_scan, "gambler": cmd_gambler, "spy": cmd_spy, "backtest": cmd_backtest}
    commands[args.cmd](args, FilterConfig())
