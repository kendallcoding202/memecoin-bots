"""Watch wallets over Solana JSON-RPC and turn their swaps into WalletTrades."""

import os

from .models import WalletTrade
from .sources import WSOL, get_json

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
LAMPORTS_PER_SOL = 1e9

# "finalized" (the RPC default) lags ~13s behind "confirmed", which is exactly the kind
# of delay that makes a copy-trade late.
COMMITMENT = "confirmed"


def rpc(method: str, params: list):
    resp = get_json(RPC_URL, data={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in resp:
        raise RuntimeError(f"{method}: {resp['error']}")
    return resp["result"]


def latest_signature(wallet: str) -> str | None:
    sigs = rpc("getSignaturesForAddress", [wallet, {"limit": 1, "commitment": COMMITMENT}])
    return sigs[0]["signature"] if sigs else None


def new_signatures(wallet: str, until: str | None = None, limit: int = 25) -> list[str]:
    """Successful signatures newer than `until`, oldest first."""
    opts = {"limit": limit, "commitment": COMMITMENT}
    if until:
        opts["until"] = until
    sigs = rpc("getSignaturesForAddress", [wallet, opts])
    return [s["signature"] for s in reversed(sigs) if not s.get("err")]


def fetch_trade(signature: str, wallet: str) -> WalletTrade | None:
    opts = {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": COMMITMENT}
    tx = rpc("getTransaction", [signature, opts])
    return parse_trade(tx, wallet, signature) if tx else None


def parse_trade(tx: dict, wallet: str, signature: str = "") -> WalletTrade | None:
    """A SOL <-> token swap by `wallet`, or None for anything else (transfers, token-to-token, failures)."""
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return None
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    if wallet not in keys:
        return None
    i = keys.index(wallet)
    # Includes the network fee and any account rent, which is noise next to a real trade.
    sol = (meta["postBalances"][i] - meta["preBalances"][i]) / LAMPORTS_PER_SOL

    deltas: dict[str, float] = {}
    for sign, balances in ((-1, meta.get("preTokenBalances")), (1, meta.get("postTokenBalances"))):
        for b in balances or []:
            if b.get("owner") != wallet:
                continue
            amount = float(b["uiTokenAmount"].get("uiAmountString") or 0)
            deltas[b["mint"]] = deltas.get(b["mint"], 0.0) + sign * amount
    sol += deltas.pop(WSOL, 0.0)  # wrapped SOL counts as SOL

    moved = {mint: d for mint, d in deltas.items() if abs(d) > 1e-12}
    if len(moved) != 1:
        return None
    [(mint, tokens)] = moved.items()
    if tokens > 0 and sol < 0:
        side = "buy"
    elif tokens < 0 and sol > 0:
        side = "sell"
    else:
        return None
    return WalletTrade(wallet, mint, side, abs(sol), abs(tokens), float(tx.get("blockTime") or 0), signature)
