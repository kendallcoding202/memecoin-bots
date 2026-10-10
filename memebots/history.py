"""Historical 5-minute candles from GeckoTerminal's free API (no key, about 30 calls a minute)."""

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .sources import WSOL, get_json

GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
CALL_GAP_S = 2.1  # stays under the free tier's rate limit
MAX_POOL_AGE_DAYS = 30  # older than this isn't a memecoin launch any more
MIN_POOL_AGE_H = 6


@dataclass
class Candle:
    ts: float  # candle open time, unix seconds
    open: float
    high: float
    low: float
    close: float
    volume_usd: float


@dataclass
class Trade:
    ts: float
    wallet: str
    side: str  # "buy" or "sell"
    price_usd: float  # token price at the fill
    volume_usd: float


@dataclass
class PoolHistory:
    pool: str
    mint: str
    symbol: str
    liquidity_usd: float  # today's liquidity: GeckoTerminal has no history for it
    created_at: float
    candles: list[Candle] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)


def load(
    days: float,
    max_pools: int,
    cache_path: str | None = None,
    min_trade_usd: float | None = None,
    min_liquidity_usd: float = 0,
) -> list[PoolHistory]:
    """Pools plus their last `days` of candles, read from `cache_path` if it exists.

    With `min_trade_usd`, also each pool's recent trades of at least that size. GeckoTerminal
    only serves the last 300 trades within 24 hours, so that's as far back as wallet data goes.
    Pools below `min_liquidity_usd` are skipped, since the filter would reject them anyway.
    """
    if cache_path and os.path.exists(cache_path):
        with open(cache_path) as f:
            raw = json.load(f)
        return [
            PoolHistory(
                **{
                    **p,
                    "candles": [Candle(**c) for c in p["candles"]],
                    "trades": [Trade(**t) for t in p.get("trades", [])],
                }
            )
            for p in raw
        ]

    since = time.time() - days * 86400
    pools = find_pools(max_pools, min_liquidity_usd)
    for n, pool in enumerate(pools, 1):
        print(f"  history {n}/{len(pools)}: {pool.symbol}", flush=True)
        pool.candles = fetch_candles(pool.pool, since)
        if min_trade_usd is not None:
            pool.trades = fetch_trades(pool, min_trade_usd)
    pools = [p for p in pools if p.candles]

    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump([asdict(p) for p in pools], f)
    return pools


def find_pools(max_pools: int, min_liquidity_usd: float = 0) -> list[PoolHistory]:
    """SOL-quoted pools launched within the last month from GeckoTerminal's trending and busiest lists.

    Brand-new pools are skipped: with minutes of history there's nothing to replay.
    """
    now = time.time()
    paths = [f"/trending_pools?page={p}&duration={d}" for d in ("24h", "6h", "1h") for p in range(1, 6)] + [
        f"/pools?page={p}&sort={s}" for s in ("h24_volume_usd_desc", "h24_tx_count_desc") for p in range(1, 11)
    ]
    found: dict[str, PoolHistory] = {}
    for path in paths:
        for pool in parse_pools(_gecko(path)):
            age = now - pool.created_at
            if (
                MIN_POOL_AGE_H * 3600 <= age <= MAX_POOL_AGE_DAYS * 86400
                and pool.liquidity_usd >= min_liquidity_usd
                and pool.mint not in found
            ):
                found[pool.mint] = pool
        if len(found) >= max_pools:
            break
    return list(found.values())[:max_pools]


def fetch_candles(pool: str, since: float) -> list[Candle]:
    candles: dict[float, Candle] = {}
    before = None
    while True:
        path = f"/pools/{pool}/ohlcv/minute?aggregate=5&limit=1000&currency=usd&token=base"
        if before:
            path += f"&before_timestamp={int(before)}"
        batch = parse_candles(_gecko(path))
        candles.update((c.ts, c) for c in batch)
        if len(batch) < 1000 or batch[0].ts <= since:
            break
        before = batch[0].ts
    return [c for _, c in sorted(candles.items()) if c.ts >= since]


def fetch_trades(pool: PoolHistory, min_usd: float) -> list[Trade]:
    return parse_trades(_gecko(f"/pools/{pool.pool}/trades?trade_volume_in_usd_greater_than={min_usd:g}"), pool.mint)


def parse_trades(data: dict, mint: str) -> list[Trade]:
    trades = []
    for row in data.get("data") or []:
        a = row.get("attributes") or {}
        if a.get("to_token_address") == mint:
            side, price = "buy", a.get("price_to_in_usd")
        elif a.get("from_token_address") == mint:
            side, price = "sell", a.get("price_from_in_usd")
        else:
            continue
        trades.append(
            Trade(_iso(a.get("block_timestamp")), a.get("tx_from_address") or "", side, _num(price), _num(a.get("volume_in_usd")))
        )
    return sorted(trades, key=lambda t: t.ts)


def parse_pools(data: dict) -> list[PoolHistory]:
    out = []
    for item in data.get("data") or []:
        attrs = item.get("attributes") or {}
        rel = item.get("relationships") or {}
        base = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
        quote = ((rel.get("quote_token") or {}).get("data") or {}).get("id", "")
        if quote != f"solana_{WSOL}" or not base.startswith("solana_") or not attrs.get("address"):
            continue
        out.append(
            PoolHistory(
                pool=attrs["address"],
                mint=base.removeprefix("solana_"),
                symbol=(attrs.get("name") or "?").split(" / ")[0],
                liquidity_usd=_num(attrs.get("reserve_in_usd")),
                created_at=_iso(attrs.get("pool_created_at")),
            )
        )
    return out


def parse_candles(data: dict) -> list[Candle]:
    rows = ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    return sorted((Candle(*map(float, row[:6])) for row in rows), key=lambda c: c.ts)


def _gecko(path: str) -> dict:
    time.sleep(CALL_GAP_S)
    return get_json(f"{GECKO}{path}")


def _iso(value) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 0.0


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
