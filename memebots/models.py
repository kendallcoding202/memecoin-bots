from dataclasses import dataclass


@dataclass
class TokenSnapshot:
    """What we know about one token at one moment, merged from the data sources."""

    mint: str
    symbol: str
    price_usd: float
    price_sol: float | None = None  # only set when the pair is quoted in SOL
    liquidity_usd: float = 0.0
    volume_1h_usd: float = 0.0
    change_1h_pct: float = 0.0
    lp_locked_pct: float | None = None  # None means unknown
    lp_lock_days: float | None = None  # days to the earliest LP unlock; inf if burned
    whale_buys_sol: list[float] | None = None  # recent buy sizes; None means no trade feed


@dataclass
class WalletTrade:
    """A SOL <-> token swap made by a wallet we're watching."""

    wallet: str
    mint: str
    side: str  # "buy" or "sell"
    sol_amount: float
    token_amount: float
    timestamp: float  # block time, unix seconds
    signature: str = ""

    @property
    def price_sol(self) -> float:
        return self.sol_amount / self.token_amount if self.token_amount else 0.0
