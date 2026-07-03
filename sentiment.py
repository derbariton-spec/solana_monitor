from __future__ import annotations

import re
from typing import Any

import requests

from config import REQUEST_TIMEOUT, USER_AGENT, load_runtime_config
from formatting import safe_float

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

BINANCE_FEAR_GREED_PAGE = "https://www.binance.com/en/square/fear-and-greed-index"
ALTERNATIVE_FNG_API = "https://api.alternative.me/fng/"
COINGLASS_ALTCOIN_SEASON_PAGE = "https://www.coinglass.com/de/pro/i/alt-coin-season"
ALTCOIN_SEASON_CANDIDATES = [
    "https://open-api-v4.coinglass.com/api/index/alt-coin-season",
    "https://open-api-v4.coinglass.com/api/indicator/alt-coin-season",
    "https://open-api-v4.coinglass.com/api/index/altcoin-season",
    "https://www.blockchaincenter.net/en/api/altcoin-season-index/",
    "https://api.blockchaincenter.net/altcoin-season-index/",
]


def _get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> requests.Response | None:
    try:
        r = requests.get(url, params=params, headers=headers or HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r
    except Exception:
        return None


def _get_json(url: str, params: dict[str, Any] | None = None, api_key: str | None = None) -> Any | None:
    headers = dict(HEADERS)
    if api_key:
        headers["CG-API-KEY"] = api_key
    r = _get(url, params=params, headers=headers)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _number_near_label(text: str, labels: list[str]) -> float | None:
    """Conservative page parser: accept only a 0-100 number very close to a label.

    This avoids false positives from gauge scales like 0/100 on rendered app shells.
    """
    normalized = re.sub(r"\s+", " ", text)
    for label in labels:
        # Label then optional punctuation/HTML escapes then number.
        pattern = rf"{label}.{{0,120}}?([0-9]{{1,3}}(?:[\.,][0-9]+)?)"
        m = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not m:
            continue
        v = safe_float(m.group(1).replace(",", "."), None)
        if v is not None and 0 <= v <= 100:
            return v
    return None


def _extract_value_from_any_json(data: Any) -> float | None:
    """Walk unknown API shapes and return a plausible 0-100 index value."""
    preferred_keys = {
        "altcoin_season_index", "altcoinSeasonIndex", "alt_coin_season", "altCoinSeason",
        "altcoin_index", "altcoinIndex", "season_index", "index", "value", "score", "now", "current", "indicator",
    }
    if isinstance(data, dict):
        for k, v in data.items():
            if k in preferred_keys:
                val = safe_float(v, None)
                if val is not None and 0 <= val <= 100:
                    return val
        for v in data.values():
            found = _extract_value_from_any_json(v)
            if found is not None:
                return found
    elif isinstance(data, list):
        # Prefer latest/current-ish rows. Many APIs are newest first; try both ends.
        candidates = data[:5] + data[-5:]
        for item in candidates:
            found = _extract_value_from_any_json(item)
            if found is not None:
                return found
    else:
        val = safe_float(data, None)
        if val is not None and 0 <= val <= 100:
            return val
    return None


def interpret_fear_greed(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 25:
        return "Extreme Fear"
    if value < 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def fetch_fear_greed() -> dict[str, Any]:
    """Fear & Greed: use a stable JSON API first; keep Binance as visual reference.

    Binance Square is rendered client-side and often returns no machine-readable index
    from Streamlit Cloud. Alternative.me provides the same type of 0-100 Crypto
    Fear & Greed value via JSON, so we use it as the reliable data source.
    """
    data = _get_json(ALTERNATIVE_FNG_API, {"limit": 1, "format": "json"})
    try:
        row = data.get("data", [])[0] if isinstance(data, dict) else None
        value = safe_float(row.get("value"), None) if isinstance(row, dict) else None
        label = row.get("value_classification") if isinstance(row, dict) else None
        if value is not None:
            return {
                "ok": True,
                "value": float(value),
                "label": label or interpret_fear_greed(float(value)),
                "timestamp": row.get("timestamp") if isinstance(row, dict) else None,
                "source": "Alternative.me Fear & Greed (Binance-Seite als Referenz)",
                "source_url": BINANCE_FEAR_GREED_PAGE,
            }
    except Exception:
        pass

    # Last resort: very conservative Binance page parser.
    r = _get(BINANCE_FEAR_GREED_PAGE)
    if r is not None:
        value = _number_near_label(r.text, [r"Crypto Fear\s*&\s*Greed Index", r"Fear\s*&\s*Greed Index", r"Fear\s*&\s*Greed"])
        if value is not None:
            return {
                "ok": True,
                "value": float(value),
                "label": interpret_fear_greed(float(value)),
                "timestamp": None,
                "source": "Binance Square Fear & Greed",
                "source_url": BINANCE_FEAR_GREED_PAGE,
            }
    return {"ok": False, "value": None, "label": "n/a", "source": "Fear & Greed nicht erreichbar", "source_url": BINANCE_FEAR_GREED_PAGE}

def interpret_altcoin_season(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 25:
        return "Bitcoin Season"
    if value < 50:
        return "neutral / BTC-lastig"
    if value < 75:
        return "Altcoins stärker"
    return "Altcoin Season"


def fetch_altcoin_season_index() -> dict[str, Any]:
    """Try CoinGlass API only when a key is configured; otherwise force proxy.

    We no longer parse CoinGlass/other HTML or loose JSON endpoints because they
    often expose gauge-scale numbers (0/100) that are not the current index. This
    was the source of the false 100.0 reading.
    """
    api_key = load_runtime_config().coinglass_api_key
    if not api_key:
        return {
            "ok": False,
            "value": None,
            "label": "Proxy aktiv",
            "source": "CoinGlass Altcoin Season benötigt API/ist nicht sauber maschinenlesbar",
            "source_url": COINGLASS_ALTCOIN_SEASON_PAGE,
        }

    for url in ALTCOIN_SEASON_CANDIDATES[:3]:
        data = _get_json(url, api_key=api_key)
        value = _extract_value_from_any_json(data)
        if value is not None and 0 <= value <= 100:
            return {"ok": True, "value": value, "label": interpret_altcoin_season(value), "source": "CoinGlass/API Altcoin Season", "source_url": COINGLASS_ALTCOIN_SEASON_PAGE}

    return {
        "ok": False,
        "value": None,
        "label": "Proxy aktiv",
        "source": "CoinGlass Altcoin Season API nicht verfügbar; Proxy aktiv",
        "source_url": COINGLASS_ALTCOIN_SEASON_PAGE,
    }

def altcoin_proxy_from_market(latest: dict | None, past: dict | None) -> dict[str, Any]:
    if not latest or not past:
        return {"ok": False, "value": None, "label": "Zu wenig Historie", "source": "Proxy"}
    sol_btc_now = safe_float(latest.get("sol_btc"), None)
    sol_btc_old = safe_float(past.get("sol_btc"), None)
    btc_dom_now = safe_float(latest.get("btc_dominance"), None)
    btc_dom_old = safe_float(past.get("btc_dominance"), None)
    if sol_btc_now is None or sol_btc_old in (None, 0):
        return {"ok": False, "value": None, "label": "Zu wenig SOL/BTC-Daten", "source": "Proxy"}
    sol_btc_change = (sol_btc_now - sol_btc_old) / sol_btc_old * 100
    btc_dom_change = None if btc_dom_now is None or btc_dom_old in (None, 0) else btc_dom_now - btc_dom_old
    proxy = 50 + sol_btc_change * 1.2
    if btc_dom_change is not None:
        proxy -= btc_dom_change * 3.0
    proxy = max(0, min(100, proxy))
    return {
        "ok": True,
        "value": proxy,
        "label": interpret_altcoin_season(proxy),
        "source": "Proxy aus SOL/BTC und BTC-Dominance",
        "source_url": COINGLASS_ALTCOIN_SEASON_PAGE,
        "sol_btc_30d_pct": sol_btc_change,
        "btc_dominance_30d_points": btc_dom_change,
    }


def sentiment_score(fear_greed: dict[str, Any], altcoin: dict[str, Any]) -> tuple[float, list[str]]:
    score = 50.0
    reasons: list[str] = []
    fg = fear_greed.get("value")
    if fg is not None:
        fg = float(fg)
        if 35 <= fg <= 65:
            score += 8
            reasons.append("Fear & Greed gesund/neutral")
        elif 20 <= fg < 35:
            score += 4
            reasons.append("Fear-Zone, antizyklisch interessant")
        elif fg < 20:
            score += 2
            reasons.append("Extreme Fear: Chance, aber hohes Risiko")
        elif 65 < fg <= 80:
            score += 2
            reasons.append("Greed, aber noch nicht extrem")
        else:
            score -= 10
            reasons.append("Extreme Greed: Überhitzungsrisiko")
    alt = altcoin.get("value")
    if alt is not None:
        alt = float(alt)
        if 50 <= alt <= 80:
            score += 10
            reasons.append("Altcoin-Phase unterstützt SOL")
        elif alt > 80:
            score += 3
            reasons.append("Altcoin Season stark, aber spätzyklisch möglich")
        elif alt < 25:
            score -= 8
            reasons.append("Bitcoin Season belastet Altcoins")
    return max(0, min(100, score)), reasons
