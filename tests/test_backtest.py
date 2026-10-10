import math
import unittest

from memebots.backtest import (
    copy_signals,
    proven,
    random_baseline,
    random_wallet_baseline,
    replay,
    replay_copies,
    score_wallets,
    snapshot_at,
    summarize,
)
from memebots.config import RiskConfig
from memebots.gambler import Gambler
from memebots.history import Candle, PoolHistory, Trade, parse_candles, parse_pools, parse_trades
from memebots.portfolio import PaperPortfolio
from memebots.sources import WSOL

SAFE = {"MEME": dict(lp_locked_pct=100.0, lp_lock_days=math.inf, top10_holder_pct=12.0, max_holder_pct=3.0, danger_risks=[])}
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
        self.assertIsNone(snapshot_at(h, ts, 11, SAFE["MEME"]))
        self.assertIsNotNone(snapshot_at(h, ts, 12, SAFE["MEME"]))

    def test_hour_change_and_volume(self):
        h = pool([1.0] * 12 + [1.2])
        snap = snapshot_at(h, [c.ts for c in h.candles], 12, SAFE["MEME"])
        self.assertAlmostEqual(snap.change_1h_pct, 20)
        self.assertEqual(snap.volume_1h_usd, 12 * 5_000)

    def test_gaps_in_candles(self):
        # Quiet pools skip candles. Change is measured from the last candle at or before an hour ago.
        h = PoolHistory("P", "MEME", "MEME", 100_000, 0, [Candle(0, 1, 1, 1, 1.0, 9), Candle(5000, 1, 2, 1, 2.0, 7)])
        snap = snapshot_at(h, [0, 5000], 1, SAFE["MEME"])
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

        return replay([h], SAFE, rule, RISK)

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
        p = replay([pool(closes)], SAFE, bot.wants_entry, RISK)
        self.assertEqual(p.closed[0].reason, "take profit")
        self.assertGreater(p.stats()["return_pct"], 0)

    def test_unlocked_tokens_never_trade(self):
        closes = [1.0] * 12 + [1.0 + 0.02 * i for i in range(1, 40)]
        bot = Gambler(PaperPortfolio(RISK))
        self.assertEqual(replay([pool(closes)], {}, bot.wants_entry, RISK).closed, [])

    def test_random_baseline_is_reproducible(self):
        h = pool([1.0, 1.1, 0.9, 1.2, 0.8, 1.3, 1.0] * 6)
        a = summarize(random_baseline([h], SAFE, 3, risk=RISK, runs=5))
        b = summarize(random_baseline([h], SAFE, 3, risk=RISK, runs=5))
        self.assertEqual(a, b)
        self.assertEqual(a["runs"], 5)


def with_trades(closes, trades):
    h = pool(closes)
    h.trades = trades
    return h


class ScoreWalletsTest(unittest.TestCase):
    # $1 for an hour, $2 for an hour, then back to $1. GOOD buys before the jump, BAD at the top.
    closes = [1.0] * 12 + [2.0] * 12 + [1.0] * 18
    trades = [Trade(t, "GOOD", "buy", 1.0, 600) for t in (0, 300, 600)] + [
        Trade(t, "BAD", "buy", 2.0, 600) for t in (3600, 3900, 4200)
    ]

    def test_scores_by_price_an_hour_later(self):
        scored = score_wallets([with_trades(self.closes, self.trades)], until=8000)
        by_wallet = {s["wallet"]: s for s in scored}
        self.assertAlmostEqual(by_wallet["GOOD"]["avg_1h_pct"], 100)
        self.assertAlmostEqual(by_wallet["BAD"]["avg_1h_pct"], -50)
        self.assertEqual([s["wallet"] for s in proven(scored)], ["GOOD"])

    def test_ignores_outcomes_after_the_cutoff(self):
        # BAD's buys only resolve after 7200s, so a 7000s cutoff can't see them.
        scored = score_wallets([with_trades(self.closes, self.trades)], until=7000)
        self.assertEqual([s["wallet"] for s in scored], ["GOOD"])


class CopyTest(unittest.TestCase):
    def test_signals_instant_and_late(self):
        h = with_trades([1.0, 1.5, 1.5], [Trade(290, "W", "buy", 1.0, 600)])
        [instant] = copy_signals([h], {"W"}, start=0, instant=True)
        self.assertEqual((instant.at, instant.price), (290, 1.0))
        [late] = copy_signals([h], {"W"}, start=0, delay_s=30)
        self.assertEqual((late.at, late.price, late.wallet_price), (320, 1.5, 1.0))
        self.assertEqual(copy_signals([h], {"W"}, start=300), [])

    def test_follows_the_copied_wallets_sell(self):
        trades = [Trade(300, "W", "buy", 1.0, 600), Trade(900, "X", "sell", 1.0, 600), Trade(1500, "W", "sell", 1.2, 600)]
        h = with_trades([1.0] * 10, trades)
        p = replay_copies([h], copy_signals([h], {"W", "X"}, 0, instant=True), SAFE, risk=RISK)
        self.assertEqual(len(p.closed), 1)
        self.assertEqual(p.closed[0].reason, "copied wallet sold")
        self.assertAlmostEqual(p.closed[0].pnl_pct, 20)

    def test_skips_chased_prices_and_filtered_tokens(self):
        h = with_trades([1.0, 1.5, 1.5, 1.5], [Trade(290, "W", "buy", 1.0, 600)])
        late = copy_signals([h], {"W"}, 0, delay_s=30)  # fills at 1.5, 50% above the wallet
        self.assertEqual(replay_copies([h], late, SAFE, risk=RISK).closed, [])
        instant = copy_signals([h], {"W"}, 0, instant=True)
        self.assertEqual(replay_copies([h], instant, {}, risk=RISK).closed, [])  # no RugCheck data
        self.assertEqual(len(replay_copies([h], instant, SAFE, risk=RISK).closed), 1)

    def test_random_wallet_baseline_is_reproducible(self):
        trades = [Trade(300 * i, f"W{i % 4}", "buy", 1.0, 600) for i in range(8)]
        h = with_trades([1.0, 1.1, 0.95, 1.2] * 3, trades)
        args = ([h], SAFE, ["W0", "W1", "W2", "W3"], 2, 0)
        self.assertEqual(
            summarize(random_wallet_baseline(*args, risk=RISK, runs=5)),
            summarize(random_wallet_baseline(*args, risk=RISK, runs=5)),
        )


class GeckoParseTest(unittest.TestCase):
    def test_parse_trades(self):
        data = {
            "data": [
                {
                    "attributes": {
                        "block_timestamp": "2026-10-09T12:00:00Z",
                        "tx_from_address": "W1",
                        "from_token_address": WSOL,
                        "to_token_address": "MEME",
                        "price_to_in_usd": "0.002",
                        "volume_in_usd": "650",
                    }
                },
                {
                    "attributes": {
                        "block_timestamp": "2026-10-09T11:00:00Z",
                        "tx_from_address": "W2",
                        "from_token_address": "MEME",
                        "to_token_address": WSOL,
                        "price_from_in_usd": "0.0019",
                        "volume_in_usd": "900",
                    }
                },
                {"attributes": {"from_token_address": "OTHER", "to_token_address": WSOL}},
            ]
        }
        trades = parse_trades(data, "MEME")
        self.assertEqual([(t.wallet, t.side, t.price_usd) for t in trades], [("W2", "sell", 0.0019), ("W1", "buy", 0.002)])

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
