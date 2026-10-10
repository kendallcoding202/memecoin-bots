"""Market data: DexScreener for price and liquidity, RugCheck for LP locks. Standard library only."""

import json
import math
import time
import urllib.error
import urllib.request

from .models import TokenSnapshot

DEXSCREENER = "https://api.dexscreener.com"
RUGCHECK = "https://api.rugcheck.xyz/v1"
WSOL = "So11111111111111111111111111111111111111112"
RUG_CACHE_S = 600
UNKNOWN_RUG_DATA = {
    "lp_locked_pct": None,
    "lp_lock_days": None,
    "top10_holder_pct": None,
    "max_holder_pct": None,
    "danger_risks": None,
}

_rug_cache: dict[str, tuple[float, dict]] = {}


def get_json(url: str, data: dict | None = None, timeout: float = 15, retries: int = 5):
    headers = {"User-Agent": "memecoin-bots/0.1", "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            # Free APIs rate limit hard and hiccup often. Back off and try again rather than failing a long run.
            if (e.code != 429 and e.code < 500) or attempt == retries:
                raise
            wait = _num(e.headers.get("Retry-After")) or 2 ** (attempt + 1)
        except OSError as e:
            # Timeouts and dropped connections are worth retrying; a host the network blocks is not.
            if "Tunnel connection failed" in str(e) or attempt == retries:
                raise
            wait = 2 ** (attempt + 1)
        time.sleep(min(wait, 60))


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


def add_rug_data(snaps, min_liquidity_usd: float = 0):
    """Add RugCheck data, skipping tokens too shallow to pass the filter anyway (RugCheck is rate limited)."""
    for snap in snaps:
        if snap.liquidity_usd >= min_liquidity_usd:
            for key, value in rug_data(snap.mint).items():
                setattr(snap, key, value)


def rug_data(mint: str, now: float | None = None) -> dict:
    """LP lock and holder fields for a TokenSnapshot. All None when RugCheck can't be reached."""
    now = now or time.time()
    hit = _rug_cache.get(mint)
    if hit and now - hit[0] < RUG_CACHE_S:
        return hit[1]
    try:
        report = get_json(f"{RUGCHECK}/tokens/{mint}/report")
    except (OSError, ValueError):
        return dict(UNKNOWN_RUG_DATA)
    locked_pct, lock_days = parse_lp_lock(report, now)
    result = {"lp_locked_pct": locked_pct, "lp_lock_days": lock_days, **parse_holders(report)}
    _rug_cache[mint] = (now, result)
    return result


def parse_holders(report: dict) -> dict:
    """How concentrated the supply is, leaving out pools and lockers, which RugCheck labels."""
    holders = report.get("topHolders")
    if not holders:
        return {"top10_holder_pct": None, "max_holder_pct": None, "danger_risks": None}
    known = report.get("knownAccounts") or {}
    pools = {addr for addr, info in known.items() if (info or {}).get("type") in ("AMM", "LOCKER")}
    pcts = sorted(
        (_num(h.get("pct")) for h in holders if h.get("owner") not in pools and h.get("address") not in pools),
        reverse=True,
    )
    return {
        "top10_holder_pct": sum(pcts[:10]),
        "max_holder_pct": pcts[0] if pcts else 0.0,
        "danger_risks": [r.get("name", "?") for r in report.get("risks") or [] if r.get("level") == "danger"],
    }


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
        lockers = list(lockers.values())
    # Big tokens have lockers on many side pools. Only the main pool's lock matters, when we can tell which it is.
    pool = main.get("pubkey")
    on_main = [lk for lk in lockers if pool and pool in (lk.get("uri") or "")]
    if on_main:
        lockers = on_main
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
