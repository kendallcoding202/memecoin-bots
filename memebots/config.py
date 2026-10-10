"""Tunable thresholds. Defaults follow the numbers in @0xboan's post where it gives one."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterConfig:
    # "checks the liquidity is locked for at least a couple of months"
    min_lp_lock_days: float = 60
    # Share of the LP that has to be locked or burned for the lock to count.
    min_lp_locked_pct: float = 90
    # "keeps the few with deep enough liquidity". The post gives no number.
    min_liquidity_usd: float = 50_000
    # Not in the post. Pump.fun LP is always burned, so on those tokens the lock check passes
    # automatically and the real rug risk is a few wallets holding enough supply to dump.
    max_top10_holder_pct: float = 30
    max_single_holder_pct: float = 10
    # "watches where whales coming in with 200-300 SOL are loading"
    whale_min_sol: float = 200
    whale_max_sol: float = 300
    # The whale check needs a per-trade feed, which isn't wired up yet (see README).
    require_whale: bool = False


@dataclass(frozen=True)
class RiskConfig:
    starting_cash_usd: float = 1_000
    # Each entry is sized off the current stack, so earlier wins grow later positions.
    position_fraction: float = 0.10
    max_open_positions: int = 5
    # Small stops, big targets: the post's 33 stops were all 10x+ smaller than its smallest big win.
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.80
    # Charged on each paper fill to stand in for fees and slippage.
    slippage_pct: float = 0.01


@dataclass(frozen=True)
class GamblerConfig:
    # Enter on 1h momentum inside this band: moving, but not already vertical.
    min_change_1h_pct: float = 5
    max_change_1h_pct: float = 60
    min_volume_1h_usd: float = 20_000


@dataclass(frozen=True)
class SpyConfig:
    # Bot Three's "late-flag bug" is copying a buy long after the wallet made it.
    # Skip signals older than this, or where price has already run past the wallet's fill.
    max_signal_age_s: float = 60
    max_chase_pct: float = 15
    # Sell when the copied wallet sells.
    follow_exits: bool = True
