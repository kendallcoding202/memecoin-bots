"""Bot Three, the Spy. Predicts nothing: copies buys from wallets you've chosen, as soon as they land on-chain."""

from .config import FilterConfig, SpyConfig
from .filter import check
from .models import TokenSnapshot, WalletTrade
from .portfolio import PaperPortfolio


class Spy:
    def __init__(
        self,
        portfolio: PaperPortfolio,
        filter_cfg: FilterConfig = FilterConfig(),
        cfg: SpyConfig = SpyConfig(),
    ):
        self.portfolio = portfolio
        self.filter_cfg = filter_cfg
        self.cfg = cfg

    def on_wallet_trade(self, trade: WalletTrade, token: TokenSnapshot | None, now: float) -> str:
        """Decide whether to copy a trade. Always returns a line saying what it did and why."""
        tag = f"{trade.wallet[:4]}.. {trade.side} {token.symbol if token else trade.mint[:8]}"
        held = self.portfolio.positions.get(trade.mint)

        if trade.side == "sell":
            if not (held and self.cfg.follow_exits):
                return f"{tag}: not holding, ignored"
            price = token.price_usd if token else held.last_price
            return f"{tag}: {self.portfolio.close(trade.mint, price, now, 'copied wallet sold')}"

        if held:
            return f"{tag}: already holding"
        if not trade.timestamp:
            return f"{tag}: skip, no block time yet"
        age = now - trade.timestamp
        if age > self.cfg.max_signal_age_s:
            return f"{tag}: skip, signal is {age:.0f}s old"
        if token is None:
            return f"{tag}: skip, no market data"
        verdict = check(token, self.filter_cfg)
        if not verdict.passed:
            return f"{tag}: skip, {'; '.join(verdict.reasons)}"
        if token.price_sol and trade.price_sol:
            chase = (token.price_sol / trade.price_sol - 1) * 100
            if chase > self.cfg.max_chase_pct:
                return f"{tag}: skip, price already {chase:.0f}% above the wallet's fill"

        pos = self.portfolio.open(trade.mint, token.symbol, token.price_usd, now)
        return f"{tag}: {pos}" if pos else f"{tag}: skip, no room for another position"

    def on_snapshot(self, token: TokenSnapshot, now: float) -> str | None:
        closed = self.portfolio.mark(token.mint, token.price_usd, now)
        return str(closed) if closed else None
