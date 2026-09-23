"""
wallet_monitor.py — Read on-chain wallet balances (read-only, no private keys).

Checks:
  - USDC on Base (EVM) via public RPC eth_call
  - USDC on Solana via public JSON-RPC getTokenAccountsByOwner
"""
from __future__ import annotations

import requests
from typing import Union
from src.config import cfg

# Contract addresses (public, on-chain)
_BASE_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_SOL_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

_TIMEOUT = 10  # seconds


def check_base_usdc() -> Union[float, str]:
    """
    Return the USDC balance (as float) of the configured Base (EVM) wallet.
    Returns an error string on failure or 'no wallet configured' if unset.
    """
    wallet = cfg.EVM_WALLET
    if not wallet:
        return "no wallet configured"

    try:
        # ERC-20 balanceOf(address) call
        padded = wallet[2:].lower().zfill(64)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [
                {
                    "to": _BASE_USDC_CONTRACT,
                    "data": f"0x70a08231{padded}",
                },
                "latest",
            ],
        }
        r = requests.post(
            "https://mainnet.base.org",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        result_hex = r.json().get("result", "0x0") or "0x0"
        return int(result_hex, 16) / 1_000_000  # USDC has 6 decimals
    except Exception as e:
        return f"err:{e}"


def check_sol_usdc() -> Union[float, str]:
    """
    Return the USDC balance (as float) of the configured Solana wallet.
    Returns an error string on failure or 'no wallet configured' if unset.
    """
    wallet = cfg.SOL_WALLET
    if not wallet:
        return "no wallet configured"

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"mint": _SOL_USDC_MINT},
                {"encoding": "jsonParsed"},
            ],
        }
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        accounts = r.json().get("result", {}).get("value", [])
        total = sum(
            float(
                a.get("account", {})
                 .get("data", {})
                 .get("parsed", {})
                 .get("info", {})
                 .get("tokenAmount", {})
                 .get("uiAmount", 0)
                or 0
            )
            for a in accounts
        )
        return total
    except Exception as e:
        return f"err:{e}"


def get_status() -> dict:
    """Return a dict with both wallet balances and totals."""
    base = check_base_usdc()
    sol = check_sol_usdc()

    base_val = base if isinstance(base, float) else 0.0
    sol_val = sol if isinstance(sol, float) else 0.0

    return {
        "base_usdc": base,
        "sol_usdc": sol,
        "total_usd": base_val + sol_val,
        "evm_wallet": cfg.EVM_WALLET or "not set",
        "sol_wallet": cfg.SOL_WALLET or "not set",
    }
