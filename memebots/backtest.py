"""Replay historical candles through the Gambler's rules, and through random entries for comparison.

Free historical data only covers tokens that are still listed today, which skews toward survivors
and flatters any strategy. The random-entry baseline runs on the same tokens with the same filter,
sizing and stops, so the gap between the two is the part you can credit to the strategy itself.
"""

import bisect
import random
import statistics
from typing import Callable

from .config import FilterConfig, RiskConfig
from .filter import check
from .history import Candle, PoolHistory
from .models import TokenSnapshot
from .portfolio import PaperPortfolio

HOUR = 3600


def snapshot_at(h: PoolHistory, timestamps: list[float], i: int, lock: tuple) -> TokenSnapshot | None:
    """What a bot would have seen at the close of candle i. None until there's an hour of history."""
    now = h.candles[i].ts
    start = bisect.bisect_right(timestamps, now - HOUR) - 1  # last candle at or before an hour ago
    if start < 0:
        return None
    then = h.candles[start].close
    return TokenSnapshot(
        mint=h.mint,
        symbol=h.symbol,
        price_usd=h.candles[i].close,
        liquidity_usd=h.liquidity_usd,
        volume_1h_usd=sum(c.volume_usd for c in h.candles[start + 1 : i + 1]),
        change_1h_pct=(h.candles[i].close / then - 1) * 100 if then > 0 else 0.0,
        lp_locked_pct=lock[0],
        lp_lock_days=lock[1],
    )


def passes_filter(h: PoolHistory, lock: tuple, cfg: FilterConfig = FilterConfig()) -> bool:
    snap = TokenSnapshot(h.mint, h.symbol, 0, liquidity_usd=h.liquidity_usd, lp_locked_pct=lock[0], lp_lock_days=lock[1])
    return check(snap, cfg).passed


def replay(
    histories: list[PoolHistory],
    locks: dict[str, tuple],
    wants_entry: Callable[[TokenSnapshot], bool],
    risk: RiskConfig = RiskConfig(),
) -> PaperPortfolio:
    portfolio = PaperPortfolio(risk)
    timestamps = {h.mint: [c.ts for c in h.candles] for h in histories}
    events = sorted(((c.ts, h, i) for h in histories for i, c in enumerate(h.candles)), key=lambda e: e[0])
    last: dict[str, Candle] = {}

    for _, h, i in events:
        candle = h.candles[i]
        last[h.mint] = candle
        if h.mint in portfolio.positions:
            _exit_or_mark(portfolio, h.mint, candle)
            continue
        snap = snapshot_at(h, timestamps[h.mint], i, locks.get(h.mint, (None, None)))
        if snap and wants_entry(snap):
            portfolio.open(h.mint, h.symbol, candle.close, candle.ts)

    for mint in list(portfolio.positions):
        portfolio.close(mint, last[mint].close, last[mint].ts, "end of test")
    return portfolio


def random_baseline(
    histories: list[PoolHistory],
    locks: dict[str, tuple],
    target_trades: int,
    filter_cfg: FilterConfig = FilterConfig(),
    risk: RiskConfig = RiskConfig(),
    runs: int = 20,
) -> list[PaperPortfolio]:
    """Random entries on filter-passing candles, tuned to make about as many trades as the strategy."""
    eligible = 0
    for h in histories:
        timestamps = [c.ts for c in h.candles]
        for i in range(len(h.candles)):
            snap = snapshot_at(h, timestamps, i, locks.get(h.mint, (None, None)))
            eligible += bool(snap and check(snap, filter_cfg).passed)
    if not eligible or not target_trades:
        return []
    p = min(1.0, target_trades / eligible)
    results = []
    for seed in range(runs):
        rng = random.Random(seed)
        results.append(replay(histories, locks, lambda s: check(s, filter_cfg).passed and rng.random() < p, risk))
    return results


def summarize(portfolios: list[PaperPortfolio]) -> dict:
    returns = [p.stats()["return_pct"] for p in portfolios]
    return {
        "runs": len(returns),
        "median_return_pct": round(statistics.median(returns), 1),
        "worst_return_pct": min(returns),
        "best_return_pct": max(returns),
        "median_trades": statistics.median(len(p.closed) for p in portfolios),
    }


def _exit_or_mark(portfolio: PaperPortfolio, mint: str, c: Candle):
    pos = portfolio.positions[mint]
    stop = pos.entry_price * (1 - portfolio.risk.stop_loss_pct)
    target = pos.entry_price * (1 + portfolio.risk.take_profit_pct)
    # Candles don't say which came first, so assume the worst: if both levels were touched, the stop was.
    # A candle that opens past a level fills at the open, like a real gap would.
    if c.low <= stop:
        portfolio.close(mint, min(c.open, stop), c.ts, "stop")
    elif c.high >= target:
        portfolio.close(mint, max(c.open, target), c.ts, "take profit")
    else:
        portfolio.mark(mint, c.close, c.ts)
