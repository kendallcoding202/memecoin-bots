import unittest

from memebots.config import RiskConfig
from memebots.portfolio import PaperPortfolio


def no_slippage(**overrides):
    return RiskConfig(**{"slippage_pct": 0, **overrides})


class PortfolioTest(unittest.TestCase):
    def test_sizes_off_the_current_stack(self):
        p = PaperPortfolio(no_slippage(position_fraction=0.1))
        self.assertAlmostEqual(p.open("A", "A", 1.0, 0).cost_usd, 100)
        p.close("A", 2.0, 1, "manual")  # +$100, equity now $1,100
        self.assertAlmostEqual(p.open("B", "B", 1.0, 2).cost_usd, 110)

    def test_stop_and_take_profit(self):
        p = PaperPortfolio(no_slippage(stop_loss_pct=0.1, take_profit_pct=0.5))
        p.open("A", "A", 1.0, 0)
        p.open("B", "B", 1.0, 0)
        self.assertIsNone(p.mark("A", 0.95, 1))
        self.assertEqual(p.mark("A", 0.89, 2).reason, "stop")
        self.assertEqual(p.mark("B", 1.6, 2).reason, "take profit")
        self.assertEqual(p.positions, {})

    def test_slippage_is_charged_both_ways(self):
        p = PaperPortfolio(RiskConfig(slippage_pct=0.01))
        p.open("A", "A", 1.0, 0)
        trade = p.close("A", 1.0, 1, "flat")
        self.assertAlmostEqual(trade.pnl_pct, (0.99 / 1.01 - 1) * 100)

    def test_respects_max_open_positions_and_duplicates(self):
        p = PaperPortfolio(no_slippage(max_open_positions=2))
        self.assertIsNotNone(p.open("A", "A", 1.0, 0))
        self.assertIsNone(p.open("A", "A", 1.0, 0))
        self.assertIsNotNone(p.open("B", "B", 1.0, 0))
        self.assertIsNone(p.open("C", "C", 1.0, 0))

    def test_tracks_drawdown_and_stats(self):
        p = PaperPortfolio(no_slippage(position_fraction=0.5, stop_loss_pct=0.9))
        p.open("A", "A", 1.0, 0)  # $500 in
        p.mark("A", 0.5, 1)  # worth $250, equity $750
        self.assertAlmostEqual(p.max_drawdown_pct, 25)
        p.close("A", 0.5, 2, "manual")
        stats = p.stats()
        self.assertEqual(stats["closed_trades"], 1)
        self.assertEqual(stats["win_rate_pct"], 0)
        self.assertEqual(stats["worst_loss_usd"], -250)


if __name__ == "__main__":
    unittest.main()
