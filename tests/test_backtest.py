import math
import unittest

from memebots.backtest import random_baseline, replay, snapshot_at, summarize
from memebots.config import RiskConfig
from memebots.gambler import Gambler
from memebots.history import Candle, PoolHistory, parse_candles, parse_pools
from memebots.portfolio import PaperPortfolio
from memebots.sources import WSOL

LOCKED = {"MEME": (100.0, math.inf)}
RISK = RiskConfig(slippage_pct=0, stop_loss_pct=0.1, take_profit_pct=0.5)


def pool(closes, volume=5_000, lows=None, highs=None, opens=None):
    candles = []
    for i, close in enumerate(closes):
        o = opens[i] if opens else (closes[i - 1] if i else close)
        lo = lows[i] if lows else min(o, close)
        hi = highs[i] if highs else max(o, close)
        candles.append(Candle(i * 300, o, hi, lo, close, volume))
    return PoolHistory("POOL", "MEME", "MEME", 100_000, 0, candles)


class SnapshotTest(unittest.TestCase):
    def test_needs_an_hour_of_history(self):
        h = pool([1.0] * 13)
        ts = [c.ts for c in h.candles]
        self.assertIsNone(snapshot_at(h, ts, 11, LOCKED["MEME"]))
        self.assertIsNotNone(snapshot_at(h, ts, 12, LOCKED["MEME"]))

    def test_hour_change_and_volume(self):
        h = pool([1.0] * 12 + [1.2])
        snap = snapshot_at(h, [c.ts for c in h.candles], 12, LOCKED["MEME"])
        self.assertAlmostEqual(snap.change_1h_pct, 20)
        self.assertEqual(snap.volume_1h_usd, 12 * 5_000)

    def test_gaps_in_candles(self):
        # Quiet pools skip candles. Change is measured from the last candle at or before an hour ago.
        h = PoolHistory("P", "MEME", "MEME", 100_000, 0, [Candle(0, 1, 1, 1, 1.0, 9), Candle(5000, 1, 2, 1, 2.0, 7)])
        snap = snapshot_at(h, [0, 5000], 1, LOCKED["MEME"])
        self.assertAlmostEqual(snap.change_1h_pct, 100)
        self.assertEqual(snap.volume_1h_usd, 7)


class ReplayTest(unittest.TestCase):
    def buy_at_12(self, h):
        bought = []

        def rule(snap):
            if not bought and snap.price_usd == h.candles[12].close:
                bought.append(True)
                return True
            return False

        return replay([h], LOCKED, rule, RISK)

    def test_take_profit(self):
        p = self.buy_at_12(pool([1.0] * 13 + [1.2, 1.6]))
        self.assertEqual(p.closed[0].reason, "take profit")
        self.assertAlmostEqual(p.closed[0].exit_price, 1.5)  # filled at the target, not the high

    def test_stop(self):
        p = self.buy_at_12(pool([1.0] * 13 + [0.95, 0.8]))
        self.assertEqual(p.closed[0].reason, "stop")
        self.assertAlmostEqual(p.closed[0].exit_price, 0.9)

    def test_candle_touching_both_levels_counts_as_stop(self):
        closes = [1.0] * 13 + [1.0]
        p = self.buy_at_12(pool(closes, lows=[1.0] * 13 + [0.5], highs=[1.0] * 13 + [2.0]))
        self.assertEqual(p.closed[0].reason, "stop")

    def test_gap_down_fills_at_open(self):
        closes = [1.0] * 13 + [0.5]
        p = self.buy_at_12(pool(closes, opens=[1.0] * 13 + [0.6]))
        self.assertAlmostEqual(p.closed[0].exit_price, 0.6)

    def test_open_positions_close_at_end(self):
        p = self.buy_at_12(pool([1.0] * 13 + [1.1]))
        self.assertEqual(p.closed[0].reason, "end of test")
        self.assertEqual(p.positions, {})

    def test_gambler_rules_on_a_pump(self):
        closes = [1.0] * 12 + [1.0 + 0.02 * i for i in range(1, 40)]
        bot = Gambler(PaperPortfolio(RISK))
        p = replay([pool(closes)], LOCKED, bot.wants_entry, RISK)
        self.assertEqual(p.closed[0].reason, "take profit")
        self.assertGreater(p.stats()["return_pct"], 0)

    def test_unlocked_tokens_never_trade(self):
        closes = [1.0] * 12 + [1.0 + 0.02 * i for i in range(1, 40)]
        bot = Gambler(PaperPortfolio(RISK))
        self.assertEqual(replay([pool(closes)], {}, bot.wants_entry, RISK).closed, [])

    def test_random_baseline_is_reproducible(self):
        h = pool([1.0, 1.1, 0.9, 1.2, 0.8, 1.3, 1.0] * 6)
        a = summarize(random_baseline([h], LOCKED, 3, risk=RISK, runs=5))
        b = summarize(random_baseline([h], LOCKED, 3, risk=RISK, runs=5))
        self.assertEqual(a, b)
        self.assertEqual(a["runs"], 5)


class GeckoParseTest(unittest.TestCase):
    def test_parse_pools_keeps_sol_pairs(self):
        data = {
            "data": [
                {
                    "attributes": {
                        "address": "POOL1",
                        "name": "MEME / SOL",
                        "reserve_in_usd": "81234.5",
                        "pool_created_at": "2026-10-08T12:00:00Z",
                    },
                    "relationships": {
                        "base_token": {"data": {"id": "solana_MEME"}},
                        "quote_token": {"data": {"id": f"solana_{WSOL}"}},
                    },
                },
                {
                    "attributes": {"address": "POOL2", "name": "X / USDC"},
                    "relationships": {
                        "base_token": {"data": {"id": "solana_X"}},
                        "quote_token": {"data": {"id": "solana_USDC"}},
                    },
                },
            ]
        }
        [p] = parse_pools(data)
        self.assertEqual((p.pool, p.mint, p.symbol, p.liquidity_usd), ("POOL1", "MEME", "MEME", 81234.5))
        self.assertGreater(p.created_at, 0)

    def test_parse_candles_sorts_oldest_first(self):
        data = {"data": {"attributes": {"ohlcv_list": [[600, 1, 2, 0.5, 1.5, 10], [300, 1, 1, 1, 1, 5]]}}}
        self.assertEqual([c.ts for c in parse_candles(data)], [300, 600])


if __name__ == "__main__":
    unittest.main()
