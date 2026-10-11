import os
import tempfile
import unittest
from unittest import mock

from memebots import launches


def pool(dex, mint, name="X / SOL"):
    return {
        "attributes": {"name": name, "address": f"POOL_{mint}", "pool_created_at": "2026-10-10T19:11:41Z"},
        "relationships": {
            "dex": {"data": {"id": dex}},
            "base_token": {"data": {"id": f"solana_{mint}"}},
        },
    }


class LaunchesTest(unittest.TestCase):
    def test_keeps_only_pump_fun_launches(self):
        data = {"data": [pool("pump-fun", "A", "AAA / SOL"), pool("meteora-dbc", "B"), pool("pumpswap", "C")]}
        found = launches.parse_new_pools(data, now=123)
        self.assertEqual(list(found), ["A"])
        self.assertEqual((found["A"]["name"], found["A"]["pool"], found["A"]["seen_at"]), ("AAA", "POOL_A", 123))
        self.assertGreater(found["A"]["created_at"], 0)

    def test_splits_bonding_curve_and_graduated_volume(self):
        pairs = [
            {"baseToken": {"address": "A"}, "dexId": "pumpfun", "volume": {"h24": 1000}},
            {"baseToken": {"address": "A"}, "dexId": "pumpswap", "volume": {"h24": 50_000}},
            {"baseToken": {"address": "B"}, "dexId": "pumpfun", "volume": {"h24": 12.5}},
        ]
        self.assertEqual(launches.parse_volumes(pairs), {"A": (1000, 50_000), "B": (12.5, 0)})

    def test_measure_recovers_graduates_launch_volume(self):
        # DexScreener lists only the PumpSwap pair for a graduated coin, so its bonding-curve
        # volume has to come from GeckoTerminal's record of the original pool.
        cohort = {
            "GRAD": {"name": "G", "pool": "POOL_GRAD", "created_at": 0, "seen_at": 60},
            "FLOP": {"name": "F", "pool": "POOL_FLOP", "created_at": 0, "seen_at": 60},
        }
        dex = [
            {"baseToken": {"address": "GRAD"}, "dexId": "pumpswap", "volume": {"h24": 90_000}},
            {"baseToken": {"address": "FLOP"}, "dexId": "pumpfun", "volume": {"h24": 40}},
        ]
        gecko = {"data": [{"attributes": {"address": "POOL_GRAD", "volume_usd": {"h24": "25000.5"}}}]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "cohort.json")
            launches.save(path, cohort)
            with (
                mock.patch("memebots.sources.get_json", return_value=dex),
                mock.patch("memebots.launches._gecko", return_value=gecko) as gecko_call,
            ):
                launches.measure(path)
            measured = launches.load(path)
        gecko_call.assert_called_once_with("/pools/multi/POOL_GRAD")
        self.assertEqual((measured["GRAD"]["bonding_volume_usd"], measured["GRAD"]["graduated_volume_usd"]), (25000.5, 90_000))
        self.assertEqual((measured["FLOP"]["bonding_volume_usd"], measured["FLOP"]["graduated_volume_usd"]), (40, 0))

    def test_creator_fees(self):
        entry = {"bonding_volume_usd": 10_000, "graduated_volume_usd": 100_000}
        self.assertAlmostEqual(launches.creator_fees(entry, 0.001), 10_000 * 0.003 + 100_000 * 0.001)

    def test_summary(self):
        entries = [
            {"created_at": 0, "measured_at": 36_000, "bonding_volume_usd": v, "graduated_volume_usd": g}
            for v, g in [(0, 0)] * 8 + [(5_000, 0), (60_000, 1_000_000)]
        ]
        s = launches.summarize(entries)
        self.assertEqual(s["coins"], 10)
        self.assertEqual(s["graduated_pct"], 10)
        self.assertEqual(s["volume_median_usd"], 0)
        self.assertEqual(s["earned_over_10_pct"], 20)  # $15 and the graduate
        self.assertEqual(s["earned_over_1000_pct"], 10)
        self.assertEqual(s["hours_since_launch_median"], 10)


if __name__ == "__main__":
    unittest.main()
