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

    args = parser.parse_args(argv)
    commands = {"scan": cmd_scan, "gambler": cmd_gambler, "spy": cmd_spy}
    commands[args.cmd](args, FilterConfig())
