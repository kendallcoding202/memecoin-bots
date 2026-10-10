"""Forward paper test for Bot One. Tokens join the test when they're first seen, not because they survived.

Each run (see .github/workflows/paper-trade.yml) looks at what's trending right now, starts tracking
new pools that pass the rug filter, appends the 5-minute candles since the last run, then replays Bot
One and the random baseline over everything collected so far and writes a report. A pool can only be
bought after it was first seen, so tokens that die later stay in the test. The backtest can't do that.

Data layout under `data_dir`:
  pools.json          every pool ever seen: when, its RugCheck data, and whether it passed the filter
  candles/<mint>.csv  5-minute candles for tracked pools, appended run by run
"""

import csv
import json
import os
import time
from datetime import datetime, timezone

from . import backtest, history, sources
from .config import FilterConfig, GamblerConfig, RiskConfig
from .filter import check
from .gambler import Gambler
from .history import Candle, PoolHistory
from .models import TokenSnapshot
from .portfolio import PaperPortfolio

TRACK_DAYS = 5  # stop fetching a pool's candles this long after first sight, to bound each run
WARMUP_S = 3600  # candles from before first sight, so the 1h momentum check has history
CANDLE_S = 300
FIELDS = ["ts", "open", "high", "low", "close", "volume_usd"]


def update(data_dir: str, filter_cfg: FilterConfig = FilterConfig(), now: float | None = None) -> dict:
    """Start tracking newly trending pools and append fresh candles for tracked ones."""
    now = now or time.time()
    index = load_index(data_dir)

    for pool in history.find_pools(500, filter_cfg.min_liquidity_usd, min_age_h=0):
        if pool.mint in index:
            continue
        rug = sources.rug_data(pool.mint)
        snap = TokenSnapshot(pool.mint, pool.symbol, 0, liquidity_usd=pool.liquidity_usd, **rug)
        index[pool.mint] = {
            "pool": pool.pool,
            "symbol": pool.symbol,
            "liquidity_usd": pool.liquidity_usd,
            "created_at": pool.created_at,
            "first_seen": now,
            "rug": rug,
            "tracked": check(snap, filter_cfg).passed,
        }
        print(f"  new: {pool.symbol} ({'tracking' if index[pool.mint]['tracked'] else 'fails filter'})", flush=True)

    for mint, meta in index.items():
        if not meta["tracked"] or now - meta["first_seen"] > TRACK_DAYS * 86400:
            continue
        path = candle_path(data_dir, mint)
        last = last_ts(path)
        since = last + CANDLE_S if last is not None else meta["first_seen"] - WARMUP_S
        try:
            candles = history.fetch_candles(meta["pool"], since)
        except (OSError, ValueError) as e:
            print(f"  candles failed for {meta['symbol']}, will catch up next run: {e}", flush=True)
            continue
        # The newest candle is still forming. Leave it for the next run so we never store a partial one.
        append_candles(path, [c for c in candles if c.ts >= since and c.ts + CANDLE_S <= now])

    save_index(data_dir, index)
    return index


def report(
    data_dir: str,
    index: dict,
    risk: RiskConfig,
    gambler_cfg: GamblerConfig = GamblerConfig(),
    filter_cfg: FilterConfig = FilterConfig(),
    now: float | None = None,
) -> str:
    now = now or time.time()
    histories, rug, not_before = load_histories(data_dir, index)
    bot = Gambler(PaperPortfolio(risk), filter_cfg, gambler_cfg)
    result = backtest.replay(histories, rug, bot.wants_entry, risk, not_before, close_at_end=False)
    baseline = backtest.random_baseline(
        histories, rug, max(len(result.closed), 1), filter_cfg, risk, not_before=not_before, close_at_end=False
    )
    started = min((meta["first_seen"] for meta in index.values()), default=now)
    return render(result, baseline, len(histories), len(index), risk, gambler_cfg, started, now)


def render(result, baseline, tracked, seen, risk, g, started, now) -> str:
    s = result.stats()
    b = backtest.summarize(baseline) if baseline else None
    days = (now - started) / 86400
    lines = [
        "# Bot One forward paper test",
        "",
        f"Fake ${risk.starting_cash_usd:,.0f}. Buys tokens up {g.min_change_1h_pct:g}–{g.max_change_1h_pct:g}% in the last hour "
        f"with ${g.min_volume_1h_usd:,.0f}+ volume, {risk.position_fraction:.0%} of equity per trade, at most "
        f"{risk.max_open_positions} open. Exits at a {risk.stop_loss_pct:.0%} stop or a {risk.take_profit_pct:.0%} target.",
        "",
        f"Started {_fmt(started)} UTC, {days:.1f} days ago. Updated {_fmt(now)} UTC. "
        f"Tracking {tracked} tokens that passed the rug filter, out of {seen} seen.",
        "",
        "|                | Bot One | Random entries, same tokens and rules |",
        "| -------------- | ------- | ------------------------------------- |",
        f"| Return         | **{s['return_pct']:+.1f}%** | "
        + (f"median {b['median_return_pct']:+.1f}% (range {b['worst_return_pct']:+.1f}% to {b['best_return_pct']:+.1f}%) |" if b else "not enough data yet |"),
        f"| Closed trades  | {s['closed_trades']} | " + (f"median {b['median_trades']:g} |" if b else "|"),
        f"| Win rate       | {_pct(s['win_rate_pct'])} | |",
        f"| Stops hit      | {s['stops']} | |",
        f"| Max drawdown   | {s['max_drawdown_pct']:.1f}% | |",
        f"| Open positions | {s['open_positions']} | |",
        "",
    ]
    if result.positions:
        lines += ["## Open positions", "", "| Token | Bought (UTC) | P&L |", "| ----- | ------------ | --- |"]
        for p in sorted(result.positions.values(), key=lambda p: p.opened_at):
            lines.append(f"| {p.symbol} | {_fmt(p.opened_at)} | {(p.last_price / p.entry_price - 1) * 100:+.1f}% |")
        lines.append("")
    if result.closed:
        lines += [
            "## Last 20 closed trades",
            "",
            "| Token | Bought (UTC) | Sold (UTC) | P&L | Why |",
            "| ----- | ------------ | ---------- | --- | --- |",
        ]
        for t in sorted(result.closed, key=lambda t: t.closed_at)[-20:][::-1]:
            lines.append(
                f"| {t.symbol} | {_fmt(t.opened_at)} | {_fmt(t.closed_at)} | {t.pnl_pct:+.1f}% (${t.pnl_usd:+,.2f}) | {t.reason} |"
            )
        lines.append("")
    lines += [
        "## How to read this",
        "",
        "- Only the gap between Bot One and the random column says anything about the strategy. Both trade the same tokens with the same filter, sizing and exits.",
        "- A token can only be bought after this test first saw it, and tokens that die stay in. That's what the backtest couldn't do.",
        "- Fills are simulated on 5-minute candles with 1% slippage each way. If a candle touched both the stop and the target, it counts as a stop.",
        "- A week or two of results is still a small sample. Give it at least 100 closed trades before trusting it either way.",
        "",
    ]
    return "\n".join(lines)


def load_histories(data_dir: str, index: dict) -> tuple[list[PoolHistory], dict, dict]:
    histories, rug, not_before = [], {}, {}
    for mint, meta in index.items():
        if not meta["tracked"]:
            continue
        candles = read_candles(candle_path(data_dir, mint))
        if not candles:
            continue
        histories.append(
            PoolHistory(meta["pool"], mint, meta["symbol"], meta["liquidity_usd"], meta["created_at"], candles)
        )
        rug[mint] = meta["rug"]
        not_before[mint] = meta["first_seen"]
    return histories, rug, not_before


def load_index(data_dir: str) -> dict:
    path = os.path.join(data_dir, "pools.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_index(data_dir: str, index: dict):
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "pools.json"), "w") as f:
        json.dump(index, f, indent=1, sort_keys=True)


def candle_path(data_dir: str, mint: str) -> str:
    return os.path.join(data_dir, "candles", f"{mint}.csv")


def read_candles(path: str) -> list[Candle]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return [Candle(*(float(row[k]) for k in FIELDS)) for row in csv.DictReader(f)]


def last_ts(path: str) -> float | None:
    candles = read_candles(path)
    return candles[-1].ts if candles else None


def append_candles(path: str, candles: list[Candle]):
    if not candles:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(FIELDS)
        for c in candles:
            writer.writerow([f"{getattr(c, k):.10g}" for k in FIELDS])


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%b %d %H:%M")


def _pct(value) -> str:
    return "-" if value is None else f"{value:.0f}%"
