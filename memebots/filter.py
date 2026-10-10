"""The rug filter every token has to get past before any bot buys it."""

from dataclasses import dataclass, field

from .config import FilterConfig
from .models import TokenSnapshot


@dataclass
class Verdict:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def check(token: TokenSnapshot, cfg: FilterConfig = FilterConfig()) -> Verdict:
    """Unknown data counts as a fail: a token we can't check is a token we don't buy."""
    # Shallow tokens never get a RugCheck lookup (it's rate limited), so stop at the liquidity reason.
    if token.liquidity_usd < cfg.min_liquidity_usd:
        return Verdict(False, [f"liquidity ${token.liquidity_usd:,.0f} < ${cfg.min_liquidity_usd:,.0f}"])

    reasons = []

    if token.lp_locked_pct is None or token.lp_lock_days is None:
        reasons.append("LP lock unknown")
    else:
        if token.lp_locked_pct < cfg.min_lp_locked_pct:
            reasons.append(f"only {token.lp_locked_pct:.0f}% of LP locked")
        if token.lp_lock_days < cfg.min_lp_lock_days:
            reasons.append(f"LP unlocks in {token.lp_lock_days:.0f} days")

    if token.top10_holder_pct is None or token.max_holder_pct is None:
        reasons.append("holders unknown")
    else:
        if token.top10_holder_pct > cfg.max_top10_holder_pct:
            reasons.append(f"top 10 wallets hold {token.top10_holder_pct:.0f}%")
        if token.max_holder_pct > cfg.max_single_holder_pct:
            reasons.append(f"one wallet holds {token.max_holder_pct:.0f}%")
    if token.danger_risks:
        reasons.append("RugCheck: " + ", ".join(token.danger_risks))

    if cfg.require_whale:
        whales = whale_buys(token, cfg)
        if whales is None:
            reasons.append("no trade feed for whale check")
        elif not whales:
            reasons.append(f"no {cfg.whale_min_sol:.0f}-{cfg.whale_max_sol:.0f} SOL buys")

    return Verdict(passed=not reasons, reasons=reasons)


def whale_buys(token: TokenSnapshot, cfg: FilterConfig = FilterConfig()) -> list[float] | None:
    if token.whale_buys_sol is None:
        return None
    return [b for b in token.whale_buys_sol if cfg.whale_min_sol <= b <= cfg.whale_max_sol]


def scan(tokens, cfg: FilterConfig = FilterConfig()) -> list[TokenSnapshot]:
    """Drop almost everything, keep the few that pass."""
    return [t for t in tokens if check(t, cfg).passed]
