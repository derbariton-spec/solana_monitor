"""Oeffentliche Datenquellen fuer den Solana Fundamental Monitor.

Ziel: Die Werte sollen moeglichst eng an die Solana-Seite von DeFiLlama
angelehnt sein. Wichtig: DeFiLlama unterscheidet zwischen Chain Fees/Revenue
und App Fees/App Revenue. Deshalb werden, soweit moeglich, beide Varianten
bereitgestellt.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

TIMEOUT = 25
HEADERS = {"User-Agent": "solana-fundamental-monitor/2.1"}

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

DEFILLAMA_CHAIN_PAGE_URL = "https://defillama.com/chain/solana"
DEFILLAMA_TVL_URL = "https://api.llama.fi/v2/historicalChainTvl/Solana"
DEFILLAMA_STABLES_CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/Solana"
DEFILLAMA_STABLES_CHAINS_URL = "https://stablecoins.llama.fi/stablecoinchains"
DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
DEFILLAMA_DEX_URL = "https://api.llama.fi/overview/dexs/Solana"
DEFILLAMA_FEES_URL = "https://api.llama.fi/overview/fees/Solana"


def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 2) -> Any | None:
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1.0 + attempt)
    return None


def get_text(url: str, retries: int = 2) -> str | None:
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1.0 + attempt)
    return None


def _parse_compact_number(raw: str, suffix: str | None = None) -> float | None:
    """Parst DeFiLlama-Strings wie 15.09b, 587,533, 2.85m."""
    if not raw:
        return None

    text = str(raw).strip().replace("$", "").replace(",", "")
    local_suffix = suffix or ""

    # Falls Suffix direkt am Wert haengt, z. B. 15.09b
    match = re.match(r"^(-?\d+(?:\.\d+)?)([kmbtKMBT]?)$", text)
    if match:
        value = float(match.group(1))
        local_suffix = match.group(2) or local_suffix
    else:
        try:
            value = float(text)
        except Exception:
            return None

    multiplier = {
        "": 1,
        "k": 1e3,
        "m": 1e6,
        "b": 1e9,
        "t": 1e12,
    }.get(local_suffix.lower(), 1)

    return value * multiplier


_CHAIN_PAGE_CACHE: dict[str, float | None] | None = None


def fetch_defillama_chain_page_metrics() -> dict[str, float | None]:
    """Liest zentrale Kennzahlen aus der sichtbaren Solana-Seite von DeFiLlama.

    Das ist absichtlich ein Fallback/Abgleich fuer Werte, die DeFiLlama zwar
    im UI zeigt, aber nicht immer sauber ueber einen dokumentierten freien API-
    Endpunkt verfuegbar macht (z. B. RWA Active Mcap, Active Addresses).
    """
    global _CHAIN_PAGE_CACHE
    if _CHAIN_PAGE_CACHE is not None:
        return _CHAIN_PAGE_CACHE

    html = get_text(DEFILLAMA_CHAIN_PAGE_URL) or ""
    compact = re.sub(r"\s+", " ", html)

    def money_after(label: str) -> float | None:
        # Beispiel: RWA Active Mcap$2.006b oder Chain Fees (24h)$587,533
        pattern = re.escape(label) + r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)([kmbtKMBT]?)"
        m = re.search(pattern, compact, flags=re.IGNORECASE)
        if not m:
            return None
        return _parse_compact_number(m.group(1), m.group(2))

    def number_after(label: str) -> float | None:
        # Beispiel: Active Addresses (24h)2.85m
        pattern = re.escape(label) + r"\s*([0-9][0-9,]*(?:\.[0-9]+)?)([kmbtKMBT]?)"
        m = re.search(pattern, compact, flags=re.IGNORECASE)
        if not m:
            return None
        return _parse_compact_number(m.group(1), m.group(2))

    _CHAIN_PAGE_CACHE = {
        "stablecoins_usd": money_after("Stablecoins Mcap"),
        "rwa_usd": money_after("RWA Active Mcap"),
        "chain_fees_usd": money_after("Chain Fees (24h)"),
        "chain_revenue_usd": money_after("Chain Revenue (24h)"),
        "app_fees_usd": money_after("App Fees (24h)"),
        "app_revenue_usd": money_after("App Revenue (24h)"),
        "dex_volume_usd": money_after("DEXs Volume (24h)"),
        "active_addresses": number_after("Active Addresses (24h)"),
        "transactions_24h": number_after("Transactions (24h)"),
        "bridged_tvl_usd": money_after("Bridged TVL"),
    }
    return _CHAIN_PAGE_CACHE


def fetch_price() -> tuple[float | None, float | None, float | None]:
    data = get_json(COINGECKO_PRICE_URL, {"ids": "solana,bitcoin", "vs_currencies": "usd,btc"})
    if not data:
        return None, None, None
    sol = data.get("solana", {})
    btc = data.get("bitcoin", {})
    return sol.get("usd"), sol.get("btc"), btc.get("usd")


def fetch_btc_dominance() -> float | None:
    data = get_json(COINGECKO_GLOBAL_URL)
    try:
        return float(data["data"]["market_cap_percentage"]["btc"])
    except Exception:
        return None


def fetch_tvl_usd() -> float | None:
    data = get_json(DEFILLAMA_TVL_URL)
    try:
        return float(data[-1]["tvl"])
    except Exception:
        return None


def fetch_stablecoins_usd() -> float | None:
    # 1) Besserer Abgleich mit DeFiLlama Chain Page, falls verfuegbar
    page_value = fetch_defillama_chain_page_metrics().get("stablecoins_usd")
    if page_value is not None:
        return page_value

    # 2) Stablecoins-by-chain API
    chains = get_json(DEFILLAMA_STABLES_CHAINS_URL)
    try:
        for chain in chains or []:
            if str(chain.get("name", "")).lower() == "solana":
                for key in ("totalCirculatingUSD", "mcap", "total", "circulating"):
                    value = chain.get(key)
                    if isinstance(value, dict):
                        return float(sum(value.values()))
                    if value is not None:
                        return float(value)
    except Exception:
        pass

    # 3) Historischer Chart als Fallback
    data = get_json(DEFILLAMA_STABLES_CHART_URL)
    try:
        last = data[-1]
        total = last.get("totalCirculatingUSD", {})
        if isinstance(total, dict):
            return float(sum(total.values()))
        return float(total)
    except Exception:
        return None


def fetch_rwa_usd() -> float | None:
    # DeFiLlama UI: RWA Active Mcap
    page_value = fetch_defillama_chain_page_metrics().get("rwa_usd")
    if page_value is not None:
        return page_value

    # Fallback: RWA-Protokolle mit Chain TVL auf Solana.
    # Achtung: Das ist NICHT identisch mit RWA Active Mcap.
    protocols = get_json(DEFILLAMA_PROTOCOLS_URL)
    if not protocols:
        return None
    total = 0.0
    for p in protocols:
        if (p.get("category") or "").lower() != "rwa":
            continue
        if "Solana" not in (p.get("chains") or []):
            continue
        total += float((p.get("chainTvls") or {}).get("Solana", 0) or 0)
    return total if total > 0 else None


def _last_total_from_llama_overview(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    for key in ("total24h", "total1d", "total7d"):
        if data.get(key) is not None:
            try:
                return float(data[key])
            except Exception:
                pass
    chart = data.get("totalDataChart") or []
    if chart:
        try:
            return float(chart[-1][1])
        except Exception:
            return None
    return None


def _protocol_value_from_overview(data: Any, protocol_name: str, category: str | None = None) -> float | None:
    if not isinstance(data, dict):
        return None
    for p in data.get("protocols", []) or []:
        name = str(p.get("name", "")).lower()
        cat = str(p.get("category", "")).lower()
        if name != protocol_name.lower():
            continue
        if category and cat != category.lower():
            continue
        for key in ("total24h", "total1d", "dailyFees", "dailyRevenue", "fees24h", "revenue24h"):
            if p.get(key) is not None:
                try:
                    return float(p[key])
                except Exception:
                    pass
    return None


def fetch_dex_volume_usd() -> float | None:
    page_value = fetch_defillama_chain_page_metrics().get("dex_volume_usd")
    if page_value is not None:
        return page_value

    data = get_json(DEFILLAMA_DEX_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyVolume"})
    return _last_total_from_llama_overview(data)


def fetch_app_fees_usd() -> float | None:
    page_value = fetch_defillama_chain_page_metrics().get("app_fees_usd")
    if page_value is not None:
        return page_value

    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"})
    return _last_total_from_llama_overview(data)


def fetch_app_revenue_usd() -> float | None:
    page_value = fetch_defillama_chain_page_metrics().get("app_revenue_usd")
    if page_value is not None:
        return page_value

    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyRevenue"})
    return _last_total_from_llama_overview(data)


def fetch_chain_fees_usd() -> float | None:
    page_value = fetch_defillama_chain_page_metrics().get("chain_fees_usd")
    if page_value is not None:
        return page_value

    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"})
    return _protocol_value_from_overview(data, "Solana", "Chain")


def fetch_chain_revenue_usd() -> float | None:
    page_value = fetch_defillama_chain_page_metrics().get("chain_revenue_usd")
    if page_value is not None:
        return page_value

    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyRevenue"})
    return _protocol_value_from_overview(data, "Solana", "Chain")


# Rueckwaertskompatibilitaet: die App nutzt bisher fees_usd/revenue_usd.
# Diese Werte sind App Fees/App Revenue, nicht Chain Fees/Revenue.
def fetch_fees_usd() -> float | None:
    return fetch_app_fees_usd()


def fetch_revenue_usd() -> float | None:
    return fetch_app_revenue_usd()


def fetch_active_addresses() -> float | None:
    return fetch_defillama_chain_page_metrics().get("active_addresses")
