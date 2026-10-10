"""Paper trading: fake money, real prices. Nothing in here touches a wallet."""

import json
import os
import time
from dataclasses import asdict, dataclass

from .config import RiskConfig


@dataclass
class Position:
    mint: str
    symbol: str
    entry_price: float  # fill price, after slippage
    qty: float
    cost_usd: float
    opened_at: float
    last_price: float

    def __str__(self):
        return f"BUY  {self.symbol} ${self.cost_usd:,.2f} @ {self.entry_price:.8g}"


@dataclass
class ClosedTrade:
    mint: str
    symbol: str
    entry_price: float
    exit_price: float
    cost_usd: float
    proceeds_usd: float
    opened_at: float
    closed_at: float
    reason: str

    @property
    def pnl_usd(self) -> float:
        return self.proceeds_usd - self.cost_usd

    @property
    def pnl_pct(self) -> float:
        return (self.proceeds_usd / self.cost_usd - 1) * 100

    def __str__(self):
        return f"SELL {self.symbol} {self.pnl_pct:+.1f}% (${self.pnl_usd:+,.2f}), {self.reason}"


class PaperPortfolio:
    def __init__(self, risk: RiskConfig = RiskConfig(), log_path: str | None = None):
        self.risk = risk
        self.cash = risk.starting_cash_usd
        self.positions: dict[str, Position] = {}
        self.closed: list[ClosedTrade] = []
        self.peak_equity = self.cash
        self.max_drawdown_pct = 0.0
        self.log_path = log_path

    def equity(self) -> float:
        return self.cash + sum(p.qty * p.last_price for p in self.positions.values())

    def open(self, mint: str, symbol: str, price: float, now: float) -> Position | None:
        if mint in self.positions or len(self.positions) >= self.risk.max_open_positions or price <= 0:
            return None
        # Sized off the whole stack, so the grind from small wins funds the big ones.
        size = min(self.equity() * self.risk.position_fraction, self.cash)
        if size <= 0:
            return None
        fill = price * (1 + self.risk.slippage_pct)
        pos = Position(mint, symbol, fill, size / fill, size, now, price)
        self.cash -= size
        self.positions[mint] = pos
        self._update_drawdown()
        self._log("open", asdict(pos))
        return pos

    def mark(self, mint: str, price: float, now: float) -> ClosedTrade | None:
        """Update a position's price and close it if it hit its stop or target."""
        pos = self.positions.get(mint)
        if pos is None or price <= 0:
            return None
        pos.last_price = price
        self._update_drawdown()
        move = price / pos.entry_price - 1
        if move <= -self.risk.stop_loss_pct:
            return self.close(mint, price, now, "stop")
        if move >= self.risk.take_profit_pct:
            return self.close(mint, price, now, "take profit")
        return None

    def close(self, mint: str, price: float, now: float, reason: str) -> ClosedTrade | None:
        pos = self.positions.pop(mint, None)
        if pos is None:
            return None
        fill = price * (1 - self.risk.slippage_pct)
        proceeds = pos.qty * fill
        self.cash += proceeds
        trade = ClosedTrade(
            pos.mint, pos.symbol, pos.entry_price, fill, pos.cost_usd, proceeds, pos.opened_at, now, reason
        )
        self.closed.append(trade)
        self._update_drawdown()
        self._log("close", {**asdict(trade), "pnl_usd": trade.pnl_usd})
        return trade

    def stats(self) -> dict:
        closed = self.closed
        wins = [t.pnl_usd for t in closed if t.pnl_usd > 0]
        equity = self.equity()
        return {
            "equity_usd": round(equity, 2),
            "return_pct": round((equity / self.risk.starting_cash_usd - 1) * 100, 1),
            "closed_trades": len(closed),
            "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
            "stops": sum(t.reason == "stop" for t in closed),
            "biggest_win_usd": round(max(wins), 2) if wins else None,
            "worst_loss_usd": round(min(t.pnl_usd for t in closed), 2) if closed else None,
            "max_drawdown_pct": round(self.max_drawdown_pct, 1),
            "open_positions": len(self.positions),
        }

    def _update_drawdown(self):
        equity = self.equity()
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (self.peak_equity - equity) / self.peak_equity * 100
        self.max_drawdown_pct = max(self.max_drawdown_pct, drawdown)

    def _log(self, event: str, data: dict):
        if not self.log_path:
            return
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"event": event, "time": time.time(), **data}) + "\n")
