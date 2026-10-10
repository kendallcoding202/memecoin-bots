"""Market data: DexScreener for price and liquidity, RugCheck for LP locks. Standard library only."""

import json
import math
import time
import urllib.request

from .models import TokenSnapshot

DEXSCREENER = "https://api.dexscreener.com"
RUGCHECK = "https://api.rugcheck.xyz/v1"
WSOL = "So11111111111111111111111111111111111111112"
LOCK_CACHE_S = 600

_lock_cache: dict[str, tuple[float, tuple[float | None, float | None]]] = {}


def get_json(url: str, data: dict | None = None, timeout: float = 15):
    headers = {"User-Agent": "memecoin-bots/0.1", "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def latest_solana_mints(limit: int = 30) -> list[str]:
    """The newest token profiles on DexScreener, Solana only."""
    profiles = get_json(f"{DEXSCREENER}/token-profiles/latest/v1")
    mints = [p["tokenAddress"] for p in profiles if p.get("chainId") == "solana" and p.get("tokenAddress")]
    return list(dict.fromkeys(mints))[:limit]


def snapshots(mints: list[str]) -> dict[str, TokenSnapshot]:
    """Price and liquidity for each mint DexScreener knows about. LP locks are added separately."""
    out = {}
    for i in range(0, len(mints), 30):  # DexScreener takes up to 30 addresses per call
        chunk = mints[i : i + 30]
        data = get_json(f"{DEXSCREENER}/tokens/v1/solana/{','.join(chunk)}")
        for mint, pair in parse_pairs(data).items():
            if mint in chunk:
                out[mint] = snapshot_from_pair(pair)
    return out


def add_lp_locks(snaps, min_liquidity_usd: float = 0):
    """Look up LP locks, skipping tokens too shallow to pass the filter anyway (RugCheck is rate limited)."""
    for snap in snaps:
        if snap.liquidity_usd >= min_liquidity_usd:
            snap.lp_locked_pct, snap.lp_lock_days = lp_lock(snap.mint)


def lp_lock(mint: str, now: float | None = None) -> tuple[float | None, float | None]:
    now = now or time.time()
    hit = _lock_cache.get(mint)
    if hit and now - hit[0] < LOCK_CACHE_S:
        return hit[1]
    try:
        result = parse_lp_lock(get_json(f"{RUGCHECK}/tokens/{mint}/report"), now)
    except (OSError, ValueError):
        return None, None
    _lock_cache[mint] = (now, result)
    return result


def parse_pairs(data) -> dict[str, dict]:
    """The most liquid pair for each base token."""
    pairs = data.get("pairs") if isinstance(data, dict) else data
    best: dict[str, dict] = {}
    for pair in pairs or []:
        mint = (pair.get("baseToken") or {}).get("address")
        if not mint:
            continue
        if mint not in best or _liquidity(pair) > _liquidity(best[mint]):
            best[mint] = pair
    return best


def snapshot_from_pair(pair: dict) -> TokenSnapshot:
    base = pair["baseToken"]
    price_native = _num(pair.get("priceNative"))
    quoted_in_sol = (pair.get("quoteToken") or {}).get("address") == WSOL
    return TokenSnapshot(
        mint=base["address"],
        symbol=base.get("symbol") or "?",
        price_usd=_num(pair.get("priceUsd")),
        price_sol=price_native if quoted_in_sol and price_native > 0 else None,
        liquidity_usd=_liquidity(pair),
        volume_1h_usd=_num((pair.get("volume") or {}).get("h1")),
        change_1h_pct=_num((pair.get("priceChange") or {}).get("h1")),
    )


def parse_lp_lock(report: dict, now: float) -> tuple[float | None, float | None]:
    """(percent of LP locked, days to the earliest unlock) from a RugCheck report. (None, None) is unknown."""
    if report.get("rugged"):
        return 0.0, 0.0
    markets = [m for m in report.get("markets") or [] if m.get("lp")]
    if not markets:
        return None, None
    main = max(markets, key=lambda m: _num(m["lp"].get("baseUSD")) + _num(m["lp"].get("quoteUSD")))
    locked_pct = _num(main["lp"].get("lpLockedPct"))

    lockers = report.get("lockers") or {}
    if isinstance(lockers, dict):
        lockers = lockers.values()
    unlocks = []
    for locker in lockers:
        ts = _num(locker.get("unlockDate"))
        if ts > 1e12:  # milliseconds
            ts /= 1000
        if ts > 0:
            unlocks.append(ts)
    if unlocks:
        return locked_pct, max((min(unlocks) - now) / 86400, 0.0)
    # Locked with no locker contract on record means the LP tokens were burned, which never unlocks.
    return locked_pct, math.inf if locked_pct > 0 else 0.0


def _liquidity(pair: dict) -> float:
    return _num((pair.get("liquidity") or {}).get("usd"))


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
