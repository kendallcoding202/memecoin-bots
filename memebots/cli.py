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
    sources.add_rug_data(snaps.values(), filter_cfg.min_liquidity_usd)
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


def load_rug(histories, filter_cfg, skip: bool) -> dict[str, dict]:
    if skip:
        print("Skipping RugCheck (--no-rug-check): every token counts as locked and widely held.")
        safe = dict(lp_locked_pct=100.0, lp_lock_days=float("inf"), top10_holder_pct=0.0, max_holder_pct=0.0, danger_risks=[])
        return {h.mint: dict(safe) for h in histories}
    rug = {h.mint: sources.rug_data(h.mint) for h in histories if h.liquidity_usd >= filter_cfg.min_liquidity_usd}
    if rug and all(r["lp_locked_pct"] is None for r in rug.values()):
        print("Warning: no RugCheck data (is api.rugcheck.xyz reachable?), so the filter will reject everything.")
    return rug


def print_stats(stats: dict):
    for key, value in stats.items():
        print(f"  {key:>18}: {value}")


def fmt(ts: float) -> str:
    return f"{datetime.fromtimestamp(ts):%b %d %H:%M}"


def cmd_backtest(args, filter_cfg):
    from . import backtest, history

    print(f"Loading {args.days:g} days of 5-minute candles for up to {args.pools} pools...")
    histories = history.load(args.days, args.pools, args.cache)
    if not histories:
        raise SystemExit("No pools with candle data.")
    rug = load_rug(histories, filter_cfg, args.no_rug_check)
    risk = RiskConfig(stop_loss_pct=args.stop, take_profit_pct=args.target)

    bot = Gambler(PaperPortfolio(risk), filter_cfg)
    result = backtest.replay(histories, rug, bot.wants_entry, risk)
    start = min(h.candles[0].ts for h in histories)
    end = max(h.candles[-1].ts for h in histories)
    print(f"\n{len(histories)} pools, {fmt(start)} to {fmt(end)}")
    passing = sum(backtest.passes_filter(h, rug.get(h.mint, {}), filter_cfg) for h in histories)
    print(f"{passing} of them pass the rug filter\n")

    print("Gambler (Bot One):")
    for trade in result.closed:
        print(f"  {fmt(trade.opened_at)}  {trade}")
    print_stats(result.stats())

    baseline = backtest.random_baseline(histories, rug, len(result.closed), filter_cfg, risk)
    if baseline:
        print("\nRandom entries, same tokens/filter/sizing/stops:")
        print_stats(backtest.summarize(baseline))


def cmd_backtest_spy(args, filter_cfg):
    from . import backtest, history

    print(f"Loading candles and ${args.min_trade_usd:g}+ trades for up to {args.pools} pools...")
    histories = history.load(1.1, args.pools, args.cache, min_trade_usd=args.min_trade_usd)
    trades = [t for h in histories for t in h.trades]
    if not trades:
        raise SystemExit("No trades found.")
    rug = load_rug(histories, filter_cfg, args.no_rug_check)
    risk = RiskConfig(stop_loss_pct=args.stop, take_profit_pct=args.target)

    # Pick wallets on the first half of the trades, then test copying them on the second half.
    first, last = min(t.ts for t in trades), max(t.ts for t in trades)
    split = first + (last - first) / 2
    scored = backtest.score_wallets(histories, until=split)
    picked = backtest.proven(scored, args.wallets)
    passing = sum(backtest.passes_filter(h, rug.get(h.mint, {}), filter_cfg) for h in histories)
    print(f"\n{len(histories)} pools ({passing} pass the rug filter), {len(trades)} trades from {fmt(first)} to {fmt(last)}")
    print(f"Picking wallets on {fmt(first)} to {fmt(split)}, testing on {fmt(split)} to {fmt(last)}")
    print(f"{len(scored)} wallets made 3+ scorable buys; {len(picked)} count as proven (avg 1h return > 0, hit rate >= 50%)")
    for s in picked[:10]:
        print(
            f"  {s['wallet'][:6]}..  {s['buys']} buys in {s['tokens']} tokens, "
            f"avg 1h {s['avg_1h_pct']:+.0f}%, hit {s['hit_rate_pct']:.0f}%"
        )
    if not picked:
        return

    wallets = {s["wallet"] for s in picked}
    runs = [
        ("instant copy, your fill = their fill (best case)", True),
        (f"realistic copy, {args.delay:g}s late, filled at that 5-min candle's close", False),
    ]
    for label, instant in runs:
        signals = backtest.copy_signals(histories, wallets, split, args.delay, instant)
        result = backtest.replay_copies(histories, signals, rug, filter_cfg, risk, start=split)
        print(f"\nCopying the proven wallets, {label}: {sum(s.side == 'buy' for s in signals)} buy signals")
        print_stats(result.stats())

    others = [s["wallet"] for s in scored if s["wallet"] not in wallets]
    baseline = backtest.random_wallet_baseline(
        histories, rug, others, len(wallets), split, filter_cfg, risk, args.delay
    )
    if baseline:
        print(f"\nCopying {len(wallets)} random other active wallets instead (realistic, 20 runs):")
        print_stats(backtest.summarize(baseline))


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
    bt.add_argument("--cache", default="runs/history.json", help="saved candles; delete to refetch")

    bts = sub.add_parser("backtest-spy", help="pick wallets on the last ~24h, copy them, compare to random wallets")
    bts.add_argument("--min-trade-usd", type=float, default=500, help="ignore trades smaller than this")
    bts.add_argument("--wallets", type=int, default=20, help="how many proven wallets to copy")
    bts.add_argument("--delay", type=float, default=30, help="seconds between their trade and ours")
    bts.add_argument("--cache", default="runs/spy-history.json", help="saved candles and trades; delete to refetch")

    for p in (bt, bts):
        p.add_argument("--pools", type=int, default=60, help="how many recent pools to test on")
        p.add_argument("--stop", type=float, default=RiskConfig.stop_loss_pct, help="stop loss, e.g. 0.25 for 25%%")
        p.add_argument("--target", type=float, default=RiskConfig.take_profit_pct, help="take profit, e.g. 1.0 for 100%%")
        p.add_argument("--no-rug-check", action="store_true", help="skip RugCheck: treat every token as safe")

    args = parser.parse_args(argv)
    commands = {
        "scan": cmd_scan,
        "gambler": cmd_gambler,
        "spy": cmd_spy,
        "backtest": cmd_backtest,
        "backtest-spy": cmd_backtest_spy,
    }
    commands[args.cmd](args, FilterConfig())
