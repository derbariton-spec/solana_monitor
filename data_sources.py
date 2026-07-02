from __future__ import annotations

import datetime as dt
import re
import time
from html import unescape
from typing import Any

import pandas as pd
import requests

from config import (
    COINBASE_CANDLES_URL,
    COINGECKO_GLOBAL_URL,
    COINGECKO_MARKET_CHART_URL,
    COINGECKO_PRICE_URL,
    COINGLASS_BASE_URL,
    COINGLASS_FUNDING_ENDPOINT,
    COINGLASS_LIQUIDATION_HEATMAP_ENDPOINT,
    COINGLASS_OPEN_INTEREST_ENDPOINT,
    COINGLASS_PAIR_HEATMAP_ENDPOINT,
    DEFILLAMA_DEX_URL,
    DEFILLAMA_FEES_URL,
    DEFILLAMA_PROTOCOLS_URL,
    DEFILLAMA_RWA_PRO_URL_TEMPLATE,
    DEFILLAMA_STABLES_URL,
    DEFILLAMA_TVL_URL,
    DEFAULT_COINGLASS_EXCHANGE,
    DEFAULT_COINGLASS_PAIR,
    DEFAULT_COINGLASS_SYMBOL,
    DEFAULT_PRODUCT_ID,
    REQUEST_TIMEOUT,
    USER_AGENT,
    load_runtime_config,
)
from formatting import safe_float

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
HTML_HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
DEFILLAMA_SOLANA_PAGE_URL = "https://defillama.com/chain/solana"
DEFILLAMA_SOLANA_RWA_PAGE_URL = "https://defillama.com/rwa/chain/solana"


def get_json(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, retries: int = 2) -> Any | None:
    merged_headers = dict(HEADERS)
    if headers:
        merged_headers.update(headers)
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, headers=merged_headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1 + attempt)
    return None


def ts_to_date(ts: int | float) -> str:
    return dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc).date().isoformat()


def fetch_live_market() -> dict[str, Any]:
    data = get_json(
        COINGECKO_PRICE_URL,
        {
            "ids": "solana,jito-staked-sol,bitcoin",
            "vs_currencies": "usd,eur,btc",
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        },
    ) or {}
    sol = data.get("solana", {})
    jito = data.get("jito-staked-sol", {})
    btc = data.get("bitcoin", {})
    return {
        "sol_usd": sol.get("usd"),
        "sol_eur": sol.get("eur"),
        "sol_btc": sol.get("btc"),
        "sol_24h_change": sol.get("usd_24h_change"),
        "sol_market_cap": sol.get("usd_market_cap"),
        "sol_volume_24h": sol.get("usd_24h_vol"),
        "jitosol_usd": jito.get("usd"),
        "jitosol_eur": jito.get("eur"),
        "jitosol_24h_change": jito.get("usd_24h_change"),
        "btc_usd": btc.get("usd"),
        "btc_eur": btc.get("eur"),
        "btc_24h_change": btc.get("usd_24h_change"),
        "timestamp": dt.datetime.now(dt.timezone.utc),
    }


def fetch_price_snapshot() -> tuple[float | None, float | None, float | None]:
    live = fetch_live_market()
    return live.get("sol_usd"), live.get("sol_btc"), live.get("btc_usd")


def fetch_btc_dominance() -> float | None:
    data = get_json(COINGECKO_GLOBAL_URL)
    try:
        return float(data["data"]["market_cap_percentage"]["btc"])
    except Exception:
        return None


def fetch_current_tvl_usd() -> float | None:
    data = get_json(DEFILLAMA_TVL_URL)
    try:
        return float(data[-1]["tvl"])
    except Exception:
        return None


def fetch_historical_tvl() -> dict[str, float]:
    data = get_json(DEFILLAMA_TVL_URL) or []
    out: dict[str, float] = {}
    for row in data:
        try:
            out[ts_to_date(row["date"])] = float(row["tvl"])
        except Exception:
            continue
    return out


def fetch_current_stablecoins_usd() -> float | None:
    data = get_json(DEFILLAMA_STABLES_URL)
    try:
        last = data[-1]
        return float(sum((last.get("totalCirculatingUSD") or {}).values()))
    except Exception:
        return None


def fetch_historical_stablecoins() -> dict[str, float]:
    data = get_json(DEFILLAMA_STABLES_URL) or []
    out: dict[str, float] = {}
    for row in data:
        try:
            total = row.get("totalCirculatingUSD", {})
            if isinstance(total, dict):
                out[ts_to_date(row["date"])] = float(sum(total.values()))
        except Exception:
            continue
    return out


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


def _history_from_llama_overview(url: str, data_type: str) -> dict[str, float]:
    data = get_json(url, {"excludeTotalDataChartBreakdown": "true", "dataType": data_type}) or {}
    chart = data.get("totalDataChart") or []
    out: dict[str, float] = {}
    for row in chart:
        try:
            out[ts_to_date(row[0])] = float(row[1])
        except Exception:
            continue
    return out


def fetch_current_dex_volume_usd() -> float | None:
    data = get_json(DEFILLAMA_DEX_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyVolume"})
    return _last_total_from_llama_overview(data)


def fetch_historical_dex_volume() -> dict[str, float]:
    return _history_from_llama_overview(DEFILLAMA_DEX_URL, "dailyVolume")


def fetch_current_app_fees_usd() -> float | None:
    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyFees"})
    return _last_total_from_llama_overview(data)


def fetch_current_app_revenue_usd() -> float | None:
    data = get_json(DEFILLAMA_FEES_URL, {"excludeTotalDataChartBreakdown": "true", "dataType": "dailyRevenue"})
    return _last_total_from_llama_overview(data)


def fetch_historical_fees(data_type: str) -> dict[str, float]:
    return _history_from_llama_overview(DEFILLAMA_FEES_URL, data_type)


def _parse_compact_number(value: str | None) -> float | None:
    """Parse strings like '$1.991b', '2.85m', '587,533' into floats."""
    if not value:
        return None
    raw = unescape(str(value)).strip().lower()
    raw = raw.replace("$", "").replace("€", "").replace(",", "").replace(" ", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)([kmbt])?", raw)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    factor = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000}.get(suffix, 1)
    return number * factor


def _fetch_defillama_page_text(url: str) -> str:
    try:
        response = requests.get(url, headers=HTML_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        text = response.text
    except Exception:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _extract_metric_from_text(text: str, labels: list[str]) -> float | None:
    if not text:
        return None
    # Supports both "RWA Active Mcap$1.991b" and "Total RWA Active Mcap $1.991b".
    for label in labels:
        pattern = re.escape(label).replace(r"\ ", r"\s*") + r"\s*\$?\s*([0-9][0-9.,]*\s*[kmbtKMBT]?)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _parse_compact_number(match.group(1))
            if value is not None:
                return value
    return None


def fetch_defillama_solana_page_metrics() -> dict[str, float | None]:
    """Best-effort parser for current Solana metrics displayed on DefiLlama.

    DefiLlama exposes RWA on public pages, while the formal RWA API is not part
    of the free endpoint list. This reads the public page text and gracefully
    returns None values if the page layout changes or blocks the request.
    """
    chain_text = _fetch_defillama_page_text(DEFILLAMA_SOLANA_PAGE_URL)
    rwa_text = _fetch_defillama_page_text(DEFILLAMA_SOLANA_RWA_PAGE_URL)

    return {
        "rwa_usd": _extract_metric_from_text(chain_text, ["RWA Active Mcap"])
        or _extract_metric_from_text(rwa_text, ["Total RWA Active Mcap", "RWA Active Mcap"]),
        "rwa_onchain_mcap_usd": _extract_metric_from_text(rwa_text, ["Total RWA Onchain Mcap", "RWA Onchain Mcap"]),
        "rwa_defi_active_tvl_usd": _extract_metric_from_text(rwa_text, ["DeFi Active TVL"]),
        "chain_fees_usd": _extract_metric_from_text(chain_text, ["Chain Fees (24h)", "Chain Fees"]),
        "chain_revenue_usd": _extract_metric_from_text(chain_text, ["Chain Revenue (24h)", "Chain Revenue"]),
        "active_addresses": _extract_metric_from_text(chain_text, ["Active Addresses (24h)", "Active Addresses"]),
        "transactions_24h": _extract_metric_from_text(chain_text, ["Transactions (24h)", "Transactions"]),
        "app_revenue_usd": _extract_metric_from_text(chain_text, ["App Revenue (24h)", "App Revenue"]),
        "app_fees_usd": _extract_metric_from_text(chain_text, ["App Fees (24h)", "App Fees"]),
    }

def fetch_current_chain_metrics_scrape_fallback() -> dict[str, Any]:
    metrics = fetch_defillama_solana_page_metrics()
    return {
        "chain_fees_usd": metrics.get("chain_fees_usd"),
        "chain_revenue_usd": metrics.get("chain_revenue_usd"),
        "active_addresses": metrics.get("active_addresses"),
        "transactions_24h": metrics.get("transactions_24h"),
    }


def fetch_rwa_active_mcap_usd() -> float | None:
    cfg = load_runtime_config()
    # Preferred path if user has DefiLlama Pro. Public DeFiLlama RWA UI exists, but historical/API
    # RWA chain endpoints are Pro-only according to DefiLlama API docs.
    if cfg.defillama_api_key:
        data = get_json(DEFILLAMA_RWA_PRO_URL_TEMPLATE.format(api_key=cfg.defillama_api_key))
        try:
            if isinstance(data, dict):
                for key in ("activeMcap", "active_mcap", "totalActiveMcap", "total_rwa_active_mcap"):
                    if data.get(key) is not None:
                        return float(data[key])
                if isinstance(data.get("data"), dict):
                    d = data["data"]
                    for key in ("activeMcap", "active_mcap", "totalActiveMcap"):
                        if d.get(key) is not None:
                            return float(d[key])
        except Exception:
            pass
    # Public current-page fallback: DefiLlama displays RWA Active Mcap on the Solana chain page.
    page_metrics = fetch_defillama_solana_page_metrics()
    if page_metrics.get("rwa_usd") is not None:
        return page_metrics.get("rwa_usd")

    # Last-resort fallback: sum protocol chain TVL for protocols marked RWA on Solana. This is NOT the
    # same as DeFiLlama RWA Active Mcap, but avoids a blank if the page/API is unavailable.
    protocols = get_json(DEFILLAMA_PROTOCOLS_URL) or []
    total = 0.0
    found = False
    for p in protocols:
        try:
            if (p.get("category") or "").lower() != "rwa":
                continue
            if "Solana" not in (p.get("chains") or []):
                continue
            total += float((p.get("chainTvls") or {}).get("Solana", 0) or 0)
            found = True
        except Exception:
            continue
    return total if found else None


def _coinbase_product_for_coin(coin_id: str) -> str | None:
    return {"solana": "SOL-USD", "bitcoin": "BTC-USD"}.get(coin_id)


def _fetch_coinbase_daily_market_chart(coin_id: str, days: int = 365) -> pd.DataFrame:
    """Fallback for SOL/BTC daily USD history using Coinbase public candles.

    Coinbase returns at most 300 candles per request, so this function downloads
    the requested period in chunks.
    """
    product_id = _coinbase_product_for_coin(coin_id)
    if not product_id:
        return pd.DataFrame()

    url = COINBASE_CANDLES_URL.format(product_id=product_id)
    end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = end - dt.timedelta(days=days + 5)
    cursor = start
    rows: list[dict[str, Any]] = []

    while cursor < end:
        batch_end = min(cursor + dt.timedelta(days=290), end)
        data = get_json(
            url,
            {
                "start": cursor.isoformat(),
                "end": batch_end.isoformat(),
                "granularity": 86400,
            },
        ) or []

        if isinstance(data, list):
            for candle in data:
                try:
                    ts, _low, _high, _open, close, _volume = candle
                    rows.append(
                        {
                            "snapshot_date": dt.datetime.fromtimestamp(
                                float(ts), tz=dt.timezone.utc
                            ).date().isoformat(),
                            coin_id + "_usd": float(close),
                        }
                    )
                except Exception:
                    continue

        cursor = batch_end + dt.timedelta(seconds=1)
        time.sleep(0.25)

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values("snapshot_date")
        .drop_duplicates("snapshot_date", keep="last")
    )


def fetch_coin_market_chart(coin_id: str, days: int = 365) -> pd.DataFrame:
    """Fetch historical USD prices for a CoinGecko coin id.

    For long public CoinGecko requests we intentionally do not force
    interval=daily. Some plans reject explicit interval overrides. If CoinGecko
    returns no usable prices, SOL/BTC fall back to Coinbase daily candles.
    """
    url = COINGECKO_MARKET_CHART_URL.format(coin_id=coin_id)

    attempts = [
        {"vs_currency": "usd", "days": str(days)},
        {"vs_currency": "usd", "days": "max"},
    ]

    rows: list[dict[str, Any]] = []
    for params in attempts:
        data = get_json(url, params) or {}
        prices = data.get("prices", []) if isinstance(data, dict) else []
        if prices:
            for item in prices:
                try:
                    ms, price = item
                    rows.append(
                        {
                            "snapshot_date": dt.datetime.fromtimestamp(
                                float(ms) / 1000, tz=dt.timezone.utc
                            ).date().isoformat(),
                            coin_id + "_usd": float(price),
                        }
                    )
                except Exception:
                    continue
            break
        time.sleep(1)

    if rows:
        df = (
            pd.DataFrame(rows)
            .sort_values("snapshot_date")
            .drop_duplicates("snapshot_date", keep="last")
        )
        # If the response is unexpectedly sparse, prefer the Coinbase fallback
        # for SOL/BTC so the backfill still produces daily rows.
        if len(df) >= min(30, max(1, int(days * 0.5))):
            return df
        fallback = _fetch_coinbase_daily_market_chart(coin_id, days)
        return fallback if not fallback.empty else df

    return _fetch_coinbase_daily_market_chart(coin_id, days)


def fetch_coinbase_candles(product_id: str = DEFAULT_PRODUCT_ID, days: int = 7, granularity: int = 3600) -> pd.DataFrame:
    # Coinbase Exchange caps responses. We request at most 300 candles, truncating range if needed.
    max_seconds = granularity * 290
    requested_seconds = int(days * 86400)
    seconds = min(requested_seconds, max_seconds)
    end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = end - dt.timedelta(seconds=seconds)
    url = COINBASE_CANDLES_URL.format(product_id=product_id)
    data = get_json(url, {"start": start.isoformat(), "end": end.isoformat(), "granularity": granularity}) or []
    rows = []
    for c in data:
        try:
            ts, low, high, open_, close, volume = c
            rows.append({"time": dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc), "open": float(open_), "high": float(high), "low": float(low), "close": float(close), "volume": float(volume)})
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("time")
    return df


def fetch_snapshot() -> dict[str, Any]:
    sol_usd, sol_btc, btc_usd = fetch_price_snapshot()
    tvl_usd = fetch_current_tvl_usd()
    stablecoins_usd = fetch_current_stablecoins_usd()
    dex_volume_usd = fetch_current_dex_volume_usd()
    app_fees_usd = fetch_current_app_fees_usd()
    app_revenue_usd = fetch_current_app_revenue_usd()
    page_metrics = fetch_defillama_solana_page_metrics()
    if app_fees_usd is None:
        app_fees_usd = page_metrics.get("app_fees_usd")
    if app_revenue_usd is None:
        app_revenue_usd = page_metrics.get("app_revenue_usd")
    chain = fetch_current_chain_metrics_scrape_fallback()
    rwa_usd = fetch_rwa_active_mcap_usd()
    if rwa_usd is None:
        rwa_usd = page_metrics.get("rwa_usd")
    btc_dominance = fetch_btc_dominance()
    tvl_sol = (tvl_usd / sol_usd) if tvl_usd and sol_usd else None
    return {
        "sol_usd": sol_usd,
        "sol_btc": sol_btc,
        "btc_usd": btc_usd,
        "btc_dominance": btc_dominance,
        "tvl_usd": tvl_usd,
        "tvl_sol": tvl_sol,
        "stablecoins_usd": stablecoins_usd,
        "rwa_usd": rwa_usd,
        "dex_volume_usd": dex_volume_usd,
        "app_fees_usd": app_fees_usd,
        "app_revenue_usd": app_revenue_usd,
        "fees_usd": app_fees_usd,
        "revenue_usd": app_revenue_usd,
        "chain_fees_usd": chain.get("chain_fees_usd"),
        "chain_revenue_usd": chain.get("chain_revenue_usd"),
        "active_addresses": chain.get("active_addresses"),
        "transactions_24h": chain.get("transactions_24h"),
    }


def fetch_coinglass_heatmap(symbol: str = DEFAULT_COINGLASS_SYMBOL, pair: str = DEFAULT_COINGLASS_PAIR, exchange: str = DEFAULT_COINGLASS_EXCHANGE, model: str = "aggregated") -> dict[str, Any]:
    cfg = load_runtime_config()
    if not cfg.coinglass_api_key:
        return {"ok": False, "message": "COINGLASS_API_KEY fehlt. Liquidation Levels werden erst mit API-Key geladen.", "data": None}
    endpoint = COINGLASS_LIQUIDATION_HEATMAP_ENDPOINT if model == "aggregated" else COINGLASS_PAIR_HEATMAP_ENDPOINT
    url = COINGLASS_BASE_URL + endpoint
    headers = {"CG-API-KEY": cfg.coinglass_api_key}
    params = {"symbol": symbol, "pair": pair, "exchange": exchange}
    data = get_json(url, params=params, headers=headers)
    if not data:
        return {"ok": False, "message": "CoinGlass lieferte keine Daten oder der Plan unterstützt den Endpoint nicht.", "data": None}
    return {"ok": True, "message": "ok", "data": data}


def summarize_liquidation_levels(heatmap: dict[str, Any], current_price: float | None = None, top_n: int = 8) -> list[dict[str, Any]]:
    if not heatmap.get("ok") or not isinstance(heatmap.get("data"), dict):
        return []
    payload = heatmap["data"].get("data", heatmap["data"])
    y_axis = payload.get("y_axis") or []
    points = payload.get("liquidation_leverage_data") or []
    levels: dict[float, float] = {}
    for p in points:
        try:
            _x_idx, y_idx, value = p
            price = float(y_axis[int(y_idx)])
            levels[price] = levels.get(price, 0.0) + float(value)
        except Exception:
            continue
    rows = [{"price": price, "liquidation_value": value, "side": "oberhalb" if current_price and price > current_price else "unterhalb" if current_price and price < current_price else "n/a"} for price, value in levels.items()]
    rows.sort(key=lambda r: r["liquidation_value"], reverse=True)
    return rows[:top_n]
