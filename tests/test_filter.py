import math
import unittest

from memebots.config import FilterConfig
from memebots.filter import check, scan
from memebots.models import TokenSnapshot


def token(**overrides):
    fields = dict(
        mint="MEME", symbol="MEME", price_usd=0.01, liquidity_usd=100_000, lp_locked_pct=100, lp_lock_days=math.inf
    )
    return TokenSnapshot(**{**fields, **overrides})


class FilterTest(unittest.TestCase):
    def test_deep_locked_token_passes(self):
        self.assertTrue(check(token()).passed)

    def test_unknown_lock_fails(self):
        verdict = check(token(lp_lock_days=None))
        self.assertFalse(verdict.passed)
        self.assertIn("LP lock unknown", verdict.reasons)

    def test_short_lock_fails(self):
        verdict = check(token(lp_lock_days=30))
        self.assertEqual(verdict.reasons, ["LP unlocks in 30 days"])

    def test_partial_lock_fails(self):
        self.assertFalse(check(token(lp_locked_pct=50)).passed)

    def test_shallow_liquidity_fails(self):
        self.assertFalse(check(token(liquidity_usd=8_000)).passed)

    def test_whale_check_when_required(self):
        cfg = FilterConfig(require_whale=True)
        self.assertIn("no trade feed for whale check", check(token(), cfg).reasons)
        self.assertFalse(check(token(whale_buys_sol=[20, 500]), cfg).passed)
        self.assertTrue(check(token(whale_buys_sol=[20, 250]), cfg).passed)

    def test_scan_keeps_only_passing(self):
        kept = scan([token(mint="A"), token(mint="B", liquidity_usd=10), token(mint="C", lp_lock_days=5)])
        self.assertEqual([t.mint for t in kept], ["A"])


if __name__ == "__main__":
    unittest.main()
