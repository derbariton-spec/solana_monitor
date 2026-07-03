from __future__ import annotations

from typing import Any

import requests

from config import REQUEST_TIMEOUT, USER_AGENT
from formatting import safe_float

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html"}
FEAR_GREED_URL = "https://api.alternative.me/fng/"
ALTCOIN_SEASON_CANDIDATES = [
    "https://www.blockchaincenter.net/en/api/altcoin-season-index/",
    "https://api.blockchaincenter.net/altcoin-season-index/",
]


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_fear_greed() -> dict[str, Any]:
    data = _get_json(FEAR_GREED_URL, {"limit": 1, "format": "json"})
    try:
        item = data["data"][0]
        return {
            "ok": True,
            "value": float(item.get("value")),
            "label": item.get("value_classification"),
            "timestamp": item.get("timestamp"),
            "source": "alternative.me",
        }
    except Exception:
        return {"ok": False, "value": None, "label": "n/a", "source": "alternative.me"}


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


def fetch_altcoin_season_index() -> dict[str, Any]:
    """Try public Altcoin Season endpoints; fall back to unavailable.

    Some providers expose this only through a website or change the endpoint.
    The app therefore treats this as optional and can still compute a proxy.
    """
    for url in ALTCOIN_SEASON_CANDIDATES:
        data = _get_json(url)
        if data is None:
            continue
        # Accept several possible shapes defensively.
        candidates = []
        if isinstance(data, dict):
            candidates.extend([data.get("altcoin_season_index"), data.get("index"), data.get("value"), data.get("score")])
            if isinstance(data.get("data"), dict):
                dd = data["data"]
                candidates.extend([dd.get("altcoin_season_index"), dd.get("index"), dd.get("value"), dd.get("score")])
        for c in candidates:
            v = safe_float(c, None)
            if v is not None and 0 <= v <= 100:
                return {"ok": True, "value": v, "label": interpret_altcoin_season(v), "source": url}
    return {"ok": False, "value": None, "label": "n/a", "source": "fallback/proxy nötig"}


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
