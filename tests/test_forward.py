import math
import tempfile
import unittest
from unittest import mock

from memebots import forward
from memebots.config import RiskConfig
from memebots.history import Candle, PoolHistory

SAFE = dict(lp_locked_pct=100.0, lp_lock_days=math.inf, top10_holder_pct=12.0, max_holder_pct=3.0, danger_risks=[])
RISK = RiskConfig(slippage_pct=0, stop_loss_pct=0.1, take_profit_pct=0.5)
NOW = 300 * 400


def candles(start, end, price=1.0):
    return [Candle(ts, price, price, price, price, 5_000) for ts in range(start, end + 1, 300)]


def pool(mint, liquidity=100_000):
    return PoolHistory(f"POOL_{mint}", mint, mint, liquidity, 0)


class StorageTest(unittest.TestCase):
    def test_append_and_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            path = forward.candle_path(d, "MEME")
            self.assertIsNone(forward.last_ts(path))
            forward.append_candles(path, candles(0, 600, 0.0012345678))
            forward.append_candles(path, candles(900, 900))
            got = forward.read_candles(path)
            self.assertEqual([c.ts for c in got], [0, 300, 600, 900])
            self.assertAlmostEqual(got[0].close, 0.0012345678)
            self.assertEqual(forward.last_ts(path), 900)


class UpdateTest(unittest.TestCase):
    def run_update(self, d, now, fetched):
        rug = {"GOOD": SAFE, "WHALE": {**SAFE, "max_holder_pct": 50.0}}
        with (
            mock.patch("memebots.history.find_pools", return_value=[pool("GOOD"), pool("WHALE")]),
            mock.patch("memebots.sources.rug_data", side_effect=lambda mint: rug[mint]),
            mock.patch("memebots.history.fetch_candles", return_value=fetched) as fetch,
        ):
            index = forward.update(d, now=now)
        return index, fetch

    def test_tracks_new_pools_and_appends_only_finished_candles(self):
        with tempfile.TemporaryDirectory() as d:
            index, fetch = self.run_update(d, NOW, candles(NOW - 3600, NOW))
            self.assertTrue(index["GOOD"]["tracked"])
            self.assertFalse(index["WHALE"]["tracked"])  # one wallet holds 50%
            fetch.assert_called_once_with("POOL_GOOD", NOW - 3600)  # an hour of warmup
            stored = forward.read_candles(forward.candle_path(d, "GOOD"))
            self.assertEqual(stored[-1].ts, NOW - 300)  # the candle opening at NOW is still forming

            later = NOW + 1200
            index, fetch = self.run_update(d, later, candles(NOW - 600, later))
            fetch.assert_called_once_with("POOL_GOOD", NOW)
            stored = forward.read_candles(forward.candle_path(d, "GOOD"))
            self.assertEqual([c.ts for c in stored[-4:]], [NOW, NOW + 300, NOW + 600, NOW + 900])
            self.assertEqual(len({c.ts for c in stored}), len(stored))  # no duplicates
            self.assertEqual(index["GOOD"]["first_seen"], NOW)  # first sighting is kept

    def test_stops_tracking_after_track_days(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_update(d, NOW, [])
            _, fetch = self.run_update(d, NOW + (forward.TRACK_DAYS + 1) * 86400, [])
            fetch.assert_not_called()


class ReportTest(unittest.TestCase):
    # Flat for an hour, then a steady climb that the Gambler should buy and ride to its target.
    pump = candles(0, 3300) + [Candle(3600 + 300 * i, 1.02**i, 1.02**i, 1.02**i, 1.02**i, 5_000) for i in range(1, 40)]

    def build(self, d, first_seen):
        forward.append_candles(forward.candle_path(d, "MEME"), self.pump)
        meta = {"pool": "P", "symbol": "MEME", "liquidity_usd": 100_000, "created_at": 0, "first_seen": first_seen}
        return {"MEME": {**meta, "rug": SAFE, "tracked": True}}

    def test_trades_after_first_sighting(self):
        with tempfile.TemporaryDirectory() as d:
            text = forward.report(d, self.build(d, first_seen=3000), RISK, now=20_000)
        self.assertIn("Last 20 closed trades", text)
        self.assertIn("take profit", text)

    def test_never_buys_before_first_sighting(self):
        with tempfile.TemporaryDirectory() as d:
            text = forward.report(d, self.build(d, first_seen=100_000), RISK, now=200_000)
        self.assertIn("| Closed trades  | 0 |", text)
        self.assertNotIn("Open positions\n", text)

    def test_empty_report(self):
        with tempfile.TemporaryDirectory() as d:
            text = forward.report(d, {}, RISK, now=NOW)
        self.assertIn("not enough data yet", text)


if __name__ == "__main__":
    unittest.main()
