from __future__ import annotations

from typing import Any

import requests

from config import JITOSOL_MINT, REQUEST_TIMEOUT, SOLANA_RPC_URL, USDC_MINT, USER_AGENT, load_runtime_config
from formatting import safe_float


def rpc_call(method: str, params: list[Any], rpc_url: str | None = None) -> dict[str, Any] | None:
    cfg = load_runtime_config()
    url = rpc_url or cfg.solana_rpc_url or SOLANA_RPC_URL
    try:
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def get_sol_balance(wallet_address: str) -> float | None:
    data = rpc_call("getBalance", [wallet_address])
    try:
        return float(data["result"]["value"]) / 1_000_000_000
    except Exception:
        return None


def get_token_accounts(wallet_address: str) -> list[dict[str, Any]]:
    data = rpc_call(
        "getTokenAccountsByOwner",
        [
            wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ],
    )
    try:
        return data["result"]["value"]
    except Exception:
        return []


def get_token_balances(wallet_address: str) -> dict[str, float]:
    balances: dict[str, float] = {}
    for account in get_token_accounts(wallet_address):
        try:
            info = account["account"]["data"]["parsed"]["info"]
            mint = info["mint"]
            amount = info["tokenAmount"].get("uiAmount")
            balances[mint] = balances.get(mint, 0.0) + safe_float(amount, 0.0)
        except Exception:
            continue
    return balances


def fetch_wallet_summary(wallet_address: str) -> dict[str, Any]:
    if not wallet_address:
        return {"ok": False, "error": "Keine Wallet-Adresse hinterlegt."}
    sol_balance = get_sol_balance(wallet_address)
    token_balances = get_token_balances(wallet_address)
    return {
        "ok": sol_balance is not None,
        "error": None if sol_balance is not None else "Wallet konnte nicht geladen werden.",
        "wallet_address": wallet_address,
        "sol_balance": sol_balance,
        "jitosol_balance": token_balances.get(JITOSOL_MINT, 0.0),
        "usdc_balance": token_balances.get(USDC_MINT, 0.0),
        "all_token_balances": token_balances,
    }
