import math
import unittest

from memebots.config import RiskConfig
from memebots.gambler import Gambler
from memebots.models import TokenSnapshot, WalletTrade
from memebots.portfolio import PaperPortfolio
from memebots.solana_rpc import parse_trade
from memebots.sources import WSOL
from memebots.spy import Spy

WALLET = "Wa11etAddress"
MINT = "MEME"


def token(**overrides):
    fields = dict(
        mint=MINT,
        symbol="MEME",
        price_usd=0.04,
        price_sol=0.00026,
        liquidity_usd=100_000,
        volume_1h_usd=50_000,
        change_1h_pct=20,
        lp_locked_pct=100,
        lp_lock_days=math.inf,
        top10_holder_pct=12,
        max_holder_pct=3,
        danger_risks=[],
    )
    return TokenSnapshot(**{**fields, **overrides})


def portfolio():
    return PaperPortfolio(RiskConfig(slippage_pct=0))


def tx(sol_before, sol_after, tokens_before, tokens_after, mint=MINT, err=None, extra_token_balances=()):
    def balance(amount, m=mint):
        return {"accountIndex": 2, "mint": m, "owner": WALLET, "uiTokenAmount": {"uiAmountString": str(amount)}}

    return {
        "blockTime": 1000,
        "meta": {
            "err": err,
            "preBalances": [5_000_000_000, int(sol_before * 1e9)],
            "postBalances": [5_000_000_000, int(sol_after * 1e9)],
            "preTokenBalances": [balance(tokens_before)] if tokens_before is not None else [],
            "postTokenBalances": [balance(tokens_after), *extra_token_balances],
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": "Payer"}, {"pubkey": WALLET}]}},
    }


class ParseTradeTest(unittest.TestCase):
    def test_buy(self):
        trade = parse_trade(tx(300, 50, None, 1_000_000), WALLET)
        self.assertEqual((trade.side, trade.mint, trade.sol_amount), ("buy", MINT, 250))
        self.assertAlmostEqual(trade.price_sol, 0.00025)

    def test_sell(self):
        self.assertEqual(parse_trade(tx(50, 300, 1_000_000, 0), WALLET).side, "sell")

    def test_wrapped_sol_counts_as_sol(self):
        # Paid in wSOL: native balance unchanged, wSOL account drops by 250.
        wsol = {"accountIndex": 3, "mint": WSOL, "owner": WALLET, "uiTokenAmount": {"uiAmountString": "0"}}
        data = tx(10, 10, None, 1_000_000, extra_token_balances=[wsol])
        data["meta"]["preTokenBalances"].append({**wsol, "uiTokenAmount": {"uiAmountString": "250"}})
        trade = parse_trade(data, WALLET)
        self.assertEqual((trade.side, trade.sol_amount), ("buy", 250))

    def test_ignores_failures_and_other_wallets(self):
        self.assertIsNone(parse_trade(tx(300, 50, None, 1_000_000, err={"x": 1}), WALLET))
        self.assertIsNone(parse_trade(tx(300, 50, None, 1_000_000), "SomeoneElse"))

    def test_ignores_token_to_token_swaps(self):
        other = {"accountIndex": 4, "mint": "OTHER", "owner": WALLET, "uiTokenAmount": {"uiAmountString": "5"}}
        self.assertIsNone(parse_trade(tx(300, 50, None, 1_000_000, extra_token_balances=[other]), WALLET))


class SpyTest(unittest.TestCase):
    buy = WalletTrade(WALLET, MINT, "buy", 250, 1_000_000, timestamp=1000)  # 0.00025 SOL per token

    def test_copies_fresh_buy(self):
        spy = Spy(portfolio())
        spy.on_wallet_trade(self.buy, token(), now=1030)
        self.assertIn(MINT, spy.portfolio.positions)

    def test_skips_stale_signal(self):
        spy = Spy(portfolio())
        self.assertIn("61s old", spy.on_wallet_trade(self.buy, token(), now=1061))
        self.assertEqual(spy.portfolio.positions, {})

    def test_skips_when_price_already_ran(self):
        spy = Spy(portfolio())
        self.assertIn("20% above", spy.on_wallet_trade(self.buy, token(price_sol=0.0003), now=1010))

    def test_skips_tokens_that_fail_the_filter(self):
        spy = Spy(portfolio())
        self.assertIn("liquidity", spy.on_wallet_trade(self.buy, token(liquidity_usd=1_000), now=1010))

    def test_follows_wallet_exit(self):
        spy = Spy(portfolio())
        spy.on_wallet_trade(self.buy, token(), now=1010)
        sell = WalletTrade(WALLET, MINT, "sell", 300, 1_000_000, timestamp=1100)
        spy.on_wallet_trade(sell, token(price_usd=0.05), now=1110)
        self.assertEqual(spy.portfolio.positions, {})
        self.assertEqual(spy.portfolio.closed[0].reason, "copied wallet sold")
        self.assertAlmostEqual(spy.portfolio.closed[0].pnl_pct, 25)


class GamblerTest(unittest.TestCase):
    def test_enters_inside_momentum_band(self):
        bot = Gambler(portfolio())
        self.assertIsNone(bot.on_snapshot(token(mint="FLAT", change_1h_pct=2), 0))
        self.assertIsNone(bot.on_snapshot(token(mint="VERTICAL", change_1h_pct=200), 0))
        self.assertIsNone(bot.on_snapshot(token(mint="THIN", volume_1h_usd=1_000), 0))
        self.assertIsNotNone(bot.on_snapshot(token(), 0))
        self.assertEqual(list(bot.portfolio.positions), [MINT])

    def test_held_position_hits_stop(self):
        bot = Gambler(portfolio())
        bot.on_snapshot(token(), 0)
        line = bot.on_snapshot(token(price_usd=0.03), 1)
        self.assertIn("stop", line)


if __name__ == "__main__":
    unittest.main()
