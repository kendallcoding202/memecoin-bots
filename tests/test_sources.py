import math
import unittest

from memebots.sources import WSOL, parse_holders, parse_lp_lock, parse_pairs, snapshot_from_pair

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW = 1_700_000_000

PAIRS = [
    {
        "baseToken": {"address": "MEME", "symbol": "MEME"},
        "quoteToken": {"address": WSOL},
        "priceNative": "0.0001",
        "priceUsd": "0.015",
        "liquidity": {"usd": 80_000},
        "volume": {"h1": 12_000},
        "priceChange": {"h1": 12.5},
    },
    {
        "baseToken": {"address": "MEME", "symbol": "MEME"},
        "quoteToken": {"address": USDC},
        "priceNative": "0.015",
        "priceUsd": "0.015",
        "liquidity": {"usd": 5_000},
    },
    {
        "baseToken": {"address": "OTHER", "symbol": "OTH"},
        "quoteToken": {"address": USDC},
        "priceNative": "2",
        "priceUsd": "2",
    },
]


class DexScreenerTest(unittest.TestCase):
    def test_picks_most_liquid_pair(self):
        for data in (PAIRS, {"pairs": PAIRS}):
            self.assertEqual(parse_pairs(data)["MEME"]["liquidity"]["usd"], 80_000)

    def test_snapshot(self):
        best = parse_pairs(PAIRS)
        meme = snapshot_from_pair(best["MEME"])
        self.assertEqual((meme.price_usd, meme.price_sol, meme.change_1h_pct), (0.015, 0.0001, 12.5))
        other = snapshot_from_pair(best["OTHER"])
        self.assertIsNone(other.price_sol)  # quoted in USDC, not SOL
        self.assertEqual(other.liquidity_usd, 0)


class RugCheckTest(unittest.TestCase):
    def test_lock_with_unlock_date(self):
        report = {"markets": [{"lp": {"lpLockedPct": 95}}], "lockers": {"x": {"unlockDate": NOW + 90 * 86400}}}
        self.assertEqual(parse_lp_lock(report, NOW), (95, 90))

    def test_unlock_date_in_milliseconds(self):
        report = {"markets": [{"lp": {"lpLockedPct": 95}}], "lockers": [{"unlockDate": (NOW + 86400) * 1000}]}
        self.assertEqual(parse_lp_lock(report, NOW), (95, 1))

    def test_only_main_pool_lockers_count(self):
        report = {
            "markets": [
                {"pubkey": "MAINPOOL", "lp": {"lpLockedPct": 99, "baseUSD": 1e6, "quoteUSD": 1e6}},
                {"pubkey": "SIDEPOOL", "lp": {"lpLockedPct": 50, "baseUSD": 10, "quoteUSD": 10}},
            ],
            "lockers": {
                "a": {"uri": "https://raydium.io/liquidity/?pool_id=MAINPOOL", "unlockDate": NOW + 200 * 86400},
                "b": {"uri": "https://raydium.io/liquidity/?pool_id=SIDEPOOL", "unlockDate": NOW + 86400},
            },
        }
        self.assertEqual(parse_lp_lock(report, NOW), (99, 200))

    def test_burned_lp_never_unlocks(self):
        self.assertEqual(parse_lp_lock({"markets": [{"lp": {"lpLockedPct": 100}}]}, NOW), (100, math.inf))

    def test_unknown_and_rugged(self):
        self.assertEqual(parse_lp_lock({}, NOW), (None, None))
        self.assertEqual(parse_lp_lock({"rugged": True}, NOW), (0, 0))


class HoldersTest(unittest.TestCase):
    def test_skips_pools_and_reads_danger_flags(self):
        report = {
            "topHolders": [
                {"owner": "POOL", "address": "a1", "pct": 40},
                {"owner": "W1", "address": "a2", "pct": 8},
                {"owner": "W2", "address": "a3", "pct": 5},
                *[{"owner": f"X{i}", "address": f"x{i}", "pct": 1} for i in range(12)],
            ],
            "knownAccounts": {"POOL": {"name": "Pump Fun AMM", "type": "AMM"}},
            "risks": [
                {"name": "Mutable metadata", "level": "warn"},
                {"name": "Freeze Authority still enabled", "level": "danger"},
            ],
        }
        out = parse_holders(report)
        self.assertEqual(out["max_holder_pct"], 8)
        self.assertEqual(out["top10_holder_pct"], 8 + 5 + 8)
        self.assertEqual(out["danger_risks"], ["Freeze Authority still enabled"])

    def test_no_holder_data_is_unknown(self):
        self.assertIsNone(parse_holders({})["top10_holder_pct"])


if __name__ == "__main__":
    unittest.main()
