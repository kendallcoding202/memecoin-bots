"""Replay history through the bots' rules, next to a random baseline on the same tokens.

Free historical data only covers tokens that are still listed today, which skews toward survivors
and flatters any strategy. Each baseline runs on the same tokens with the same filter, sizing and
stops, so the gap between strategy and baseline is the part you can credit to the strategy itself.

`rug` arguments map a mint to the RugCheck fields from sources.rug_data(). RugCheck only knows a
token's current state, so the backtest filters on today's locks and holders, not those at the time.
"""

import bisect
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from .config import FilterConfig, RiskConfig, SpyConfig
from .filter import check
from .history import Candle, PoolHistory
from .models import TokenSnapshot
from .portfolio import PaperPortfolio

HOUR = 3600


def snapshot_at(h: PoolHistory, timestamps: list[float], i: int, rug: dict) -> TokenSnapshot | None:
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
        **rug,
    )


def passes_filter(h: PoolHistory, rug: dict, cfg: FilterConfig = FilterConfig()) -> bool:
    return check(TokenSnapshot(h.mint, h.symbol, 0, liquidity_usd=h.liquidity_usd, **rug), cfg).passed


# Bot One: entries decided candle by candle.


def replay(
    histories: list[PoolHistory],
    rug: dict[str, dict],
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
        snap = snapshot_at(h, timestamps[h.mint], i, rug.get(h.mint, {}))
        if snap and wants_entry(snap):
            portfolio.open(h.mint, h.symbol, candle.close, candle.ts)

    _close_all(portfolio, last)
    return portfolio


def random_baseline(
    histories: list[PoolHistory],
    rug: dict[str, dict],
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
            snap = snapshot_at(h, timestamps, i, rug.get(h.mint, {}))
            eligible += bool(snap and check(snap, filter_cfg).passed)
    if not eligible or not target_trades:
        return []
    p = min(1.0, target_trades / eligible)
    results = []
    for seed in range(runs):
        rng = random.Random(seed)
        results.append(replay(histories, rug, lambda s: check(s, filter_cfg).passed and rng.random() < p, risk))
    return results


# Bot Three: entries and exits driven by other wallets' trades.


@dataclass
class Signal:
    at: float  # when we act on it
    mint: str
    side: str
    price: float  # our fill, before slippage
    wallet_price: float  # the copied wallet's fill
    wallet: str


def price_at(h: PoolHistory, timestamps: list[float], t: float) -> float | None:
    """Close of the 5-minute candle containing t. None if no candle covers it."""
    i = bisect.bisect_right(timestamps, t) - 1
    if i < 0 or t - h.candles[i].ts > 600:
        return None
    return h.candles[i].close


def score_wallets(histories: list[PoolHistory], until: float, horizon: float = HOUR, min_buys: int = 3) -> list[dict]:
    """Rate wallets by how the price moved in the hour after each of their buys, best first.

    Only buys whose hour was over before `until` count, so nothing after `until` leaks into the pick.
    """
    returns: dict[str, list[float]] = defaultdict(list)
    tokens: dict[str, set] = defaultdict(set)
    for h in histories:
        timestamps = [c.ts for c in h.candles]
        for t in h.trades:
            if t.side != "buy" or t.price_usd <= 0 or t.ts + horizon > until:
                continue
            later = price_at(h, timestamps, t.ts + horizon)
            if later:
                returns[t.wallet].append(later / t.price_usd - 1)
                tokens[t.wallet].add(h.mint)
    scored = [
        {
            "wallet": wallet,
            "buys": len(r),
            "tokens": len(tokens[wallet]),
            "avg_1h_pct": statistics.mean(r) * 100,
            "hit_rate_pct": 100 * sum(x > 0 for x in r) / len(r),
        }
        for wallet, r in returns.items()
        if len(r) >= min_buys
    ]
    return sorted(scored, key=lambda s: -s["avg_1h_pct"])


def proven(scored: list[dict], top: int = 20) -> list[dict]:
    return [s for s in scored if s["avg_1h_pct"] > 0 and s["hit_rate_pct"] >= 50][:top]


def copy_signals(
    histories: list[PoolHistory], wallets: set[str], start: float, delay_s: float = 30, instant: bool = False
) -> list[Signal]:
    """The copied wallets' trades from `start` on, as we'd act on them.

    `instant` fills at the wallet's own price, the best case. Otherwise we see the trade `delay_s`
    late and fill at the close of that 5-minute candle, since candles are as fine as the data goes.
    """
    signals = []
    for h in histories:
        timestamps = [c.ts for c in h.candles]
        for t in h.trades:
            if t.wallet not in wallets or t.ts < start:
                continue
            if instant:
                at, price = t.ts, t.price_usd
            else:
                at, price = t.ts + delay_s, price_at(h, timestamps, t.ts + delay_s)
            if price:
                signals.append(Signal(at, h.mint, t.side, price, t.price_usd, t.wallet))
    return signals


def replay_copies(
    histories: list[PoolHistory],
    signals: list[Signal],
    rug: dict[str, dict],
    filter_cfg: FilterConfig = FilterConfig(),
    risk: RiskConfig = RiskConfig(),
    spy_cfg: SpyConfig = SpyConfig(),
    start: float = 0.0,
) -> PaperPortfolio:
    portfolio = PaperPortfolio(risk)
    pools = {h.mint: h for h in histories}
    copied_from: dict[str, str] = {}
    # Candles sort before signals at the same time, so a position's first exit check is the next candle.
    events = [(c.ts, 0, h.mint, c) for h in histories for c in h.candles if c.ts >= start - 300]
    events += [(s.at, 1, s.mint, s) for s in signals]
    events.sort(key=lambda e: (e[0], e[1]))
    last: dict[str, Candle] = {}

    for at, kind, mint, item in events:
        if kind == 0:
            last[mint] = item
            if mint in portfolio.positions:
                _exit_or_mark(portfolio, mint, item)
            continue
        if item.side == "sell":
            if spy_cfg.follow_exits and mint in portfolio.positions and copied_from.get(mint) == item.wallet:
                portfolio.close(mint, item.price, at, "copied wallet sold")
            continue
        if mint in portfolio.positions:
            continue
        h = pools[mint]
        snap = TokenSnapshot(mint, h.symbol, item.price, liquidity_usd=h.liquidity_usd, **rug.get(mint, {}))
        if not check(snap, filter_cfg).passed:
            continue
        if item.price > item.wallet_price * (1 + spy_cfg.max_chase_pct / 100):
            continue  # the late-flag guard: price already ran past the wallet's fill
        if portfolio.open(mint, h.symbol, item.price, at):
            copied_from[mint] = item.wallet

    _close_all(portfolio, last)
    return portfolio


def random_wallet_baseline(
    histories: list[PoolHistory],
    rug: dict[str, dict],
    candidates: list[str],
    n_wallets: int,
    start: float,
    filter_cfg: FilterConfig = FilterConfig(),
    risk: RiskConfig = RiskConfig(),
    delay_s: float = 30,
    runs: int = 20,
) -> list[PaperPortfolio]:
    """Copy `n_wallets` picked at random from `candidates`, the same way the proven ones are copied."""
    candidates = sorted(candidates)
    if not candidates:
        return []
    results = []
    for seed in range(runs):
        picked = set(random.Random(seed).sample(candidates, min(n_wallets, len(candidates))))
        signals = copy_signals(histories, picked, start, delay_s)
        results.append(replay_copies(histories, signals, rug, filter_cfg, risk, start=start))
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


def _close_all(portfolio: PaperPortfolio, last: dict[str, Candle]):
    for mint in list(portfolio.positions):
        candle = last.get(mint)
        price = candle.close if candle else portfolio.positions[mint].last_price
        portfolio.close(mint, price, candle.ts if candle else 0, "end of test")
