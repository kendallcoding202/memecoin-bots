import unittest

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
