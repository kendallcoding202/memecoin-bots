"""Bot One, the Gambler. Bets on direction: buys filtered tokens that are already moving up."""

from .config import FilterConfig, GamblerConfig
from .filter import check
from .models import TokenSnapshot
from .portfolio import PaperPortfolio


class Gambler:
    def __init__(
        self,
        portfolio: PaperPortfolio,
        filter_cfg: FilterConfig = FilterConfig(),
        cfg: GamblerConfig = GamblerConfig(),
    ):
        self.portfolio = portfolio
        self.filter_cfg = filter_cfg
        self.cfg = cfg

    def wants_entry(self, token: TokenSnapshot) -> bool:
        return (
            check(token, self.filter_cfg).passed
            and self.cfg.min_change_1h_pct <= token.change_1h_pct <= self.cfg.max_change_1h_pct
            and token.volume_1h_usd >= self.cfg.min_volume_1h_usd
        )

    def on_snapshot(self, token: TokenSnapshot, now: float) -> str | None:
        """Returns a line to print when something happened, otherwise None."""
        if token.mint in self.portfolio.positions:
            closed = self.portfolio.mark(token.mint, token.price_usd, now)
            return str(closed) if closed else None
        if not self.wants_entry(token):
            return None

        pos = self.portfolio.open(token.mint, token.symbol, token.price_usd, now)
        return f"{pos} (1h {token.change_1h_pct:+.0f}%)" if pos else None
