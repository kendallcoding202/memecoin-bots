"""What does launching a pump.fun coin actually earn its creator? Follow a cohort of launches from birth.

collect: poll GeckoTerminal's newest pools and record every pump.fun launch, about 8 minutes after it
         was created, before anyone knows how it will do. Coins that die stay in the sample.
measure: a day later, total each coin's 24h trading volume across all its pools on DexScreener
         (the bonding curve, plus PumpSwap if it graduated) and turn that into creator fees.

Fee rates are from pump.fun/docs/fees: the creator gets 0.30% of bonding-curve volume. After
graduation the creator's cut is tiered by market cap, from 0.95% for small coins down to 0.05%.
"""

import json
import os
import statistics
import time

from . import sources
from .history import _gecko, _iso

BONDING_CURVE_FEE = 0.003
GRADUATED_FEE_LOW, GRADUATED_FEE_HIGH = 0.0005, 0.0095


def collect(path: str, minutes: float, every_s: float = 600, pages: int = 5) -> dict:
    cohort = load(path)
    end = time.time() + minutes * 60
    while True:
        before = len(cohort)
        for page in range(1, pages + 1):
            try:
                found = parse_new_pools(_gecko(f"/new_pools?page={page}"), time.time())
            except (OSError, ValueError) as e:
                print(f"  page {page} failed: {e}", flush=True)
                continue
            for mint, entry in found.items():
                cohort.setdefault(mint, entry)
        save(path, cohort)
        print(f"  {time.strftime('%H:%M:%S')}  +{len(cohort) - before} launches, {len(cohort)} total", flush=True)
        if time.time() + every_s > end:
            return cohort
        time.sleep(every_s)


def parse_new_pools(data: dict, now: float) -> dict:
    out = {}
    for row in data.get("data") or []:
        rel = row.get("relationships") or {}
        if ((rel.get("dex") or {}).get("data") or {}).get("id") != "pump-fun":
            continue
        base = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
        attrs = row.get("attributes") or {}
        if not base.startswith("solana_"):
            continue
        out[base.removeprefix("solana_")] = {
            "name": (attrs.get("name") or "?").split(" / ")[0],
            "pool": attrs.get("address"),
            "created_at": _iso(attrs.get("pool_created_at")),
            "seen_at": now,
        }
    return out


def measure(path: str) -> dict:
    """Add each coin's current 24h volume to the cohort file and return summary stats."""
    cohort = load(path)
    mints = list(cohort)
    found = {}
    for i in range(0, len(mints), 30):
        data = sources.get_json(f"{sources.DEXSCREENER}/tokens/v1/solana/{','.join(mints[i : i + 30])}")
        for mint, volumes in parse_volumes(data).items():
            found[mint] = volumes
    # DexScreener drops a coin's pump.fun pair once it graduates, which would leave out the
    # launch-phase trading of exactly the coins that did best. GeckoTerminal still has the pool.
    graduates = {cohort[m]["pool"]: m for m, (bonding, grad) in found.items() if grad > 0 and bonding == 0}
    for pool, volume in bonding_volumes(list(graduates)).items():
        mint = graduates.get(pool)
        if mint:
            found[mint] = (volume, found[mint][1])
    now = time.time()
    for mint, entry in cohort.items():
        bonding, graduated = found.get(mint, (0.0, 0.0))
        entry.update(measured_at=now, bonding_volume_usd=bonding, graduated_volume_usd=graduated, listed=mint in found)
    save(path, cohort)
    return summarize(list(cohort.values()))


def bonding_volumes(pools: list[str]) -> dict[str, float]:
    """24h volume of pump.fun bonding-curve pools, by pool address, from GeckoTerminal."""
    out = {}
    for i in range(0, len(pools), 30):
        data = _gecko(f"/pools/multi/{','.join(pools[i : i + 30])}")
        for row in data.get("data") or []:
            attrs = row.get("attributes") or {}
            if attrs.get("address"):
                out[attrs["address"]] = sources._num((attrs.get("volume_usd") or {}).get("h24"))
    return out


def parse_volumes(data) -> dict[str, tuple[float, float]]:
    """24h volume per coin: (on the pump.fun bonding curve, on any pool after graduating)."""
    pairs = data.get("pairs") if isinstance(data, dict) else data
    out: dict[str, list[float]] = {}
    for pair in pairs or []:
        mint = (pair.get("baseToken") or {}).get("address")
        if not mint:
            continue
        vol = sources._num((pair.get("volume") or {}).get("h24"))
        slot = out.setdefault(mint, [0.0, 0.0])
        slot[0 if pair.get("dexId") == "pumpfun" else 1] += vol
    return {mint: (v[0], v[1]) for mint, v in out.items()}


def creator_fees(entry: dict, graduated_rate: float) -> float:
    return entry.get("bonding_volume_usd", 0) * BONDING_CURVE_FEE + entry.get("graduated_volume_usd", 0) * graduated_rate


def summarize(entries: list[dict]) -> dict:
    measured = [e for e in entries if "measured_at" in e]
    if not measured:
        return {"coins": 0}
    volume = sorted(e["bonding_volume_usd"] + e["graduated_volume_usd"] for e in measured)
    fees = sorted(creator_fees(e, (GRADUATED_FEE_LOW + GRADUATED_FEE_HIGH) / 2) for e in measured)
    n = len(measured)

    def pct(xs, p):
        return round(xs[min(n - 1, int(p / 100 * n))], 2)

    return {
        "coins": n,
        "hours_since_launch_median": round(statistics.median((e["measured_at"] - e["created_at"]) / 3600 for e in measured), 1),
        "graduated_pct": round(100 * sum(e["graduated_volume_usd"] > 0 for e in measured) / n, 1),
        "volume_median_usd": pct(volume, 50),
        "volume_p90_usd": pct(volume, 90),
        "volume_p99_usd": pct(volume, 99),
        "volume_max_usd": round(volume[-1], 2),
        "fees_median_usd": pct(fees, 50),
        "fees_p90_usd": pct(fees, 90),
        "fees_p99_usd": pct(fees, 99),
        "fees_max_usd": round(fees[-1], 2),
        "fees_mean_usd": round(statistics.mean(fees), 2),
        "earned_over_10_pct": round(100 * sum(f > 10 for f in fees) / n, 1),
        "earned_over_100_pct": round(100 * sum(f > 100 for f in fees) / n, 1),
        "earned_over_1000_pct": round(100 * sum(f > 1000 for f in fees) / n, 1),
        "fees_range_note": f"graduated volume charged at the {GRADUATED_FEE_LOW:.2%}-{GRADUATED_FEE_HIGH:.2%} midpoint",
    }


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save(path: str, cohort: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(cohort, f, indent=1, sort_keys=True)
