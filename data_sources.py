"""Oeffentliche Datenquellen fuer den Solana Fundamental Monitor.

Die Funktionen sind bewusst fehlertolerant: wenn ein Endpunkt ausfaellt, wird None
zurueckgegeben. Der Score ignoriert fehlende Werte automatisch.
"""

from __future__ import annotations

import time
from typing import Any

import requests

TIMEOUT = 25
HEADERS = {"User-Agent": "solana-fundamental-monitor/2.0"}

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
DEFILLAMA_TVL_URL = "https://api.llama.fi/v2/historicalChainTvl/Solana"
DEFILLAMA_STABLES_URL = "https://stablecoins.llama.fi/stablecoincharts/Solana"
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
    data = get_json(DEFILLAMA_STABLES_URL)
    try:
        last = data[-1]
        return float(sum(last.get("totalCirculatingUSD", {}).values()))
    except Exception:
        return None


def fetch_rwa_usd() -> float | None:
    """DefiLlama-nahe RWA-Schaetzung: RWA-Protokolle mit Chain TVL auf Solana.

    Hinweis: RWA.xyz kann andere Abgrenzungen verwenden. Deshalb im Dashboard als
    DefiLlama-RWA-Schaetzung kennzeichnen.
    """
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
    return total


def _last_total_from_llama_overview(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    # Neue DefiLlama Overview APIs liefern oft total24h oder totalDataChart.
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


def fetch_dex_volume_usd() -> float | None:
    data = get_json(DEFILLAMA_DEX_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyVolume"})
    return _last_total_from_llama_overview(data)


def fetch_fees_usd() -> float | None:
    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"})
    return _last_total_from_llama_overview(data)


def fetch_revenue_usd() -> float | None:
    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyRevenue"})
    return _last_total_from_llama_overview(data)


def fetch_active_addresses() -> float | None:
    # Platzhalter fuer Artemis/Flipside. Wird im Score automatisch ignoriert.
    return None
