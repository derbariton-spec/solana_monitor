from __future__ import annotations

from typing import Any

import pandas as pd
import requests

from config import REQUEST_TIMEOUT, USER_AGENT
from formatting import safe_float
from sentiment import altcoin_proxy_from_market, fetch_altcoin_season_index, fetch_fear_greed, sentiment_score
from technicals import technical_score, technical_summary

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
BINANCE_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_OI_URL = "https://fapi.binance.com/fapi/v1/openInterest"
BINANCE_OI_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_binance_funding(symbol: str = "SOLUSDT") -> dict[str, Any]:
    premium = _get_json(BINANCE_PREMIUM_INDEX_URL, {"symbol": symbol}) or {}
    hist = _get_json(BINANCE_FUNDING_URL, {"symbol": symbol, "limit": 20}) or []
    value = safe_float(premium.get("lastFundingRate"), None)
    rows = []
    if isinstance(hist, list):
        for h in hist:
            v = safe_float(h.get("fundingRate"), None)
            if v is not None:
                rows.append(v)
    avg = sum(rows) / len(rows) if rows else None
    return {
        "ok": value is not None or avg is not None,
        "symbol": symbol,
        "funding_rate": value,
        "funding_rate_pct": None if value is None else value * 100,
        "avg_funding_rate": avg,
        "avg_funding_rate_pct": None if avg is None else avg * 100,
        "source": "Binance Futures public API",
    }


def fetch_binance_open_interest(symbol: str = "SOLUSDT") -> dict[str, Any]:
    cur = _get_json(BINANCE_OI_URL, {"symbol": symbol}) or {}
    hist = _get_json(BINANCE_OI_HIST_URL, {"symbol": symbol, "period": "1d", "limit": 31}) or []
    current_oi = safe_float(cur.get("openInterest"), None)
    change = None
    if isinstance(hist, list) and len(hist) >= 2:
        first = safe_float(hist[0].get("sumOpenInterest"), None)
        last = safe_float(hist[-1].get("sumOpenInterest"), current_oi)
        if first not in (None, 0) and last is not None:
            change = (last - first) / first * 100
    return {
        "ok": current_oi is not None,
        "symbol": symbol,
        "open_interest_contracts": current_oi,
        "open_interest_30d_pct": change,
        "source": "Binance Futures public API",
    }


def interpret_funding(funding_pct: float | None) -> str:
    if funding_pct is None:
        return "n/a"
    if funding_pct < -0.02:
        return "Short-lastig"
    if funding_pct <= 0.015:
        return "neutral/gesund"
    if funding_pct <= 0.05:
        return "long-lastig"
    return "stark long crowded"


def derivatives_score(funding: dict[str, Any], oi: dict[str, Any]) -> tuple[float, list[str]]:
    score = 50.0
    reasons: list[str] = []
    f = funding.get("funding_rate_pct")
    oi_chg = oi.get("open_interest_30d_pct")
    if f is not None:
        f = float(f)
        if -0.01 <= f <= 0.015:
            score += 12
            reasons.append("Funding neutral/gesund")
        elif 0.015 < f <= 0.05:
            score -= 4
            reasons.append("Funding positiv: Longs zahlen, leicht crowded")
        elif f > 0.05:
            score -= 18
            reasons.append("Funding stark positiv: Long-Crowding")
        elif f < -0.02:
            score += 6
            reasons.append("Negative Funding kann antizyklisch bullisch sein")
    if oi_chg is not None:
        oi_chg = float(oi_chg)
        if oi_chg > 20 and f is not None and f > 0.015:
            score -= 14
            reasons.append("Open Interest steigt stark bei positiver Funding")
        elif oi_chg > 10:
            score -= 4
            reasons.append("Open Interest steigt: Hebel nimmt zu")
        elif oi_chg < -10:
            score += 4
            reasons.append("Open Interest sinkt: weniger Hebel im Markt")
    return max(0, min(100, score)), reasons


def build_market_signal_report(candles: pd.DataFrame, latest: dict | None = None, past: dict | None = None, symbol: str = "SOLUSDT") -> dict[str, Any]:
    tech = technical_summary(candles)
    tech_score, tech_reasons = technical_score(tech)
    funding = fetch_binance_funding(symbol)
    oi = fetch_binance_open_interest(symbol)
    deriv_score, deriv_reasons = derivatives_score(funding, oi)
    fear = fetch_fear_greed()
    altcoin = fetch_altcoin_season_index()
    if not altcoin.get("ok"):
        altcoin = altcoin_proxy_from_market(latest, past)
    sent_score, sent_reasons = sentiment_score(fear, altcoin)
    timing_score = round(tech_score * 0.45 + deriv_score * 0.30 + sent_score * 0.25, 1)
    risk_score = round(100 - max(0, (50 - deriv_score) * 0.7 + max(0, (50 - sent_score) * 0.3)), 1)
    if timing_score >= 70:
        label = "bullisch"
    elif timing_score >= 56:
        label = "vorsichtig bullisch"
    elif timing_score >= 45:
        label = "neutral"
    elif timing_score >= 35:
        label = "riskant / schwach"
    else:
        label = "bearish / überhitzt"
    return {
        "timing_score": timing_score,
        "risk_score": max(0, min(100, risk_score)),
        "label": label,
        "technical_score": round(tech_score, 1),
        "derivatives_score": round(deriv_score, 1),
        "sentiment_score": round(sent_score, 1),
        "technical": tech,
        "funding": funding,
        "open_interest": oi,
        "fear_greed": fear,
        "altcoin_season": altcoin,
        "reasons_positive": [r for r in tech_reasons + deriv_reasons + sent_reasons if not any(x in r.lower() for x in ["crowding", "überhit", "bearish", "schwach", "bitcoin season", "belastet"])],
        "reasons_risk": [r for r in tech_reasons + deriv_reasons + sent_reasons if any(x in r.lower() for x in ["crowding", "überhit", "bearish", "schwach", "bitcoin season", "belastet", "hebel"])],
    }


def signal_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    tech = report.get("technical") or {}
    funding = report.get("funding") or {}
    oi = report.get("open_interest") or {}
    fear = report.get("fear_greed") or {}
    alt = report.get("altcoin_season") or {}
    return [
        {"Signal": "RSI 14", "Wert": None if tech.get("rsi_14") is None else round(float(tech.get("rsi_14")), 1), "Interpretation": tech.get("rsi_label", "n/a"), "Quelle": "Coinbase Daily Candles"},
        {"Signal": "MACD", "Wert": None if tech.get("macd_histogram") is None else round(float(tech.get("macd_histogram")), 4), "Interpretation": (tech.get("macd_cross") or {}).get("label"), "Quelle": "Coinbase Daily Candles"},
        {"Signal": "Candlestick", "Wert": "", "Interpretation": (tech.get("engulfing") or {}).get("label"), "Quelle": "Coinbase Daily Candles"},
        {"Signal": "Funding Rate", "Wert": None if funding.get("funding_rate_pct") is None else f"{float(funding.get('funding_rate_pct')):.4f}%", "Interpretation": interpret_funding(funding.get("funding_rate_pct")), "Quelle": funding.get("source")},
        {"Signal": "Open Interest 30D", "Wert": None if oi.get("open_interest_30d_pct") is None else f"{float(oi.get('open_interest_30d_pct')):.2f}%", "Interpretation": "steigend" if (oi.get("open_interest_30d_pct") or 0) > 5 else "fallend/neutral", "Quelle": oi.get("source")},
        {"Signal": "Fear & Greed", "Wert": fear.get("value"), "Interpretation": fear.get("label"), "Quelle": fear.get("source")},
        {"Signal": "Altcoin Season", "Wert": None if alt.get("value") is None else round(float(alt.get("value")), 1), "Interpretation": alt.get("label"), "Quelle": alt.get("source")},
    ]
