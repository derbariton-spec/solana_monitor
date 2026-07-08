from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import requests

from config import REQUEST_TIMEOUT, USER_AGENT
from formatting import fmt_pct, fmt_usd, safe_float

HEADERS = {
    "User-Agent": f"Mozilla/5.0 {USER_AGENT}",
    "Accept": "application/json,text/csv,text/html",
}
STOOQ_QUOTE_URL = "https://stooq.com/q/l/"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CME_FEDWATCH_URL = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"

MACRO_QUOTES = {
    "wti_oil": {"fred_id": "DCOILWTICO", "symbol": "CL=F", "stooq_symbol": "cl.f", "label": "WTI Oil", "kind": "usd"},
    "brent_oil": {"fred_id": "DCOILBRENTEU", "symbol": "BZ=F", "stooq_symbol": "bz.f", "label": "Brent Oil", "kind": "usd"},
    "dxy": {"fred_id": "DTWEXBGS", "symbol": "DX-Y.NYB", "stooq_symbol": "dx.f", "label": "Trade Weighted US Dollar", "kind": "number"},
    "us_2y": {"fred_id": "DGS2", "symbol": "^IRX", "stooq_symbol": "2usy.b", "label": "US 2Y Yield", "kind": "pct"},
    "us_10y": {"fred_id": "DGS10", "symbol": "^TNX", "stooq_symbol": "10usy.b", "label": "US 10Y Yield", "kind": "pct"},
}

GEOPOLITICAL_FEEDS = {
    "Google News: Geopolitics Oil": "https://news.google.com/rss/search?q=oil%20geopolitical%20risk%20OR%20middle%20east%20risk%20when:7d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Iran Risk": "https://news.google.com/rss/search?q=Iran%20oil%20shipping%20sanctions%20when:14d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Fed Inflation": "https://news.google.com/rss/search?q=Federal%20Reserve%20inflation%20yields%20when:7d&hl=en-US&gl=US&ceid=US:en",
}

GEOPOLITICAL_RISK_WORDS = [
    "war", "attack", "strike", "sanction", "sanctions", "missile", "escalation",
    "iran", "strait of hormuz", "shipping", "oil shock", "ceasefire", "tariff",
]


def _get(url: str, params: dict[str, Any] | None = None) -> requests.Response | None:
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response
    except Exception:
        return None


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any | None:
    response = _get(url, params=params)
    if response is None:
        return None
    try:
        return response.json()
    except Exception:
        return None


def _post_json(url: str, payload: dict[str, Any]) -> Any | None:
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def _csv_row(text: str) -> dict[str, str] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    headers = [h.strip() for h in lines[0].split(",")]
    values = [v.strip() for v in lines[1].split(",")]
    if len(headers) != len(values):
        return None
    return dict(zip(headers, values))


def _fred_points(text: str, series_id: str) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for line in text.splitlines()[1:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        date, raw_value = parts[0], parts[1]
        value = safe_float(raw_value, None)
        if value is not None:
            points.append((date, value))
    return points


def fetch_fred_quote(series_id: str, label: str, kind: str = "number") -> dict[str, Any]:
    response = _get(FRED_CSV_URL, {"id": series_id})
    points = _fred_points(response.text, series_id) if response is not None else []
    current = points[-1][1] if points else None
    previous = points[-2][1] if len(points) >= 2 else None
    change_pct = ((current - previous) / previous * 100) if current is not None and previous not in (None, 0) else None
    return {
        "ok": current is not None,
        "key": series_id,
        "label": label,
        "value": current,
        "change_pct": change_pct,
        "kind": kind,
        "date": points[-1][0] if points else None,
        "source": "FRED",
        "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
    }


def fetch_stooq_quote(symbol: str, label: str, kind: str = "number") -> dict[str, Any]:
    response = _get(STOOQ_QUOTE_URL, {"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
    row = _csv_row(response.text) if response is not None else None
    close = safe_float((row or {}).get("Close"), None)
    open_ = safe_float((row or {}).get("Open"), None)
    change_pct = ((close - open_) / open_ * 100) if close is not None and open_ not in (None, 0) else None
    return {
        "ok": close is not None,
        "key": symbol,
        "label": label,
        "value": close,
        "change_pct": change_pct,
        "kind": kind,
        "date": (row or {}).get("Date"),
        "source": "Stooq",
        "source_url": f"https://stooq.com/q/?s={symbol}",
    }


def fetch_yahoo_quote(symbol: str, label: str, kind: str = "number") -> dict[str, Any]:
    data = _get_json(YAHOO_CHART_URL.format(symbol=quote(symbol, safe="")), {"range": "5d", "interval": "1d"})
    try:
        result = data["chart"]["result"][0]
        meta = result.get("meta") or {}
        close_values = [safe_float(v, None) for v in (result.get("indicators", {}).get("quote", [{}])[0].get("close") or [])]
        close_values = [v for v in close_values if v is not None]
        current = safe_float(meta.get("regularMarketPrice"), None) or (close_values[-1] if close_values else None)
        previous = close_values[-2] if len(close_values) >= 2 else safe_float(meta.get("chartPreviousClose"), None)
        change_pct = ((current - previous) / previous * 100) if current is not None and previous not in (None, 0) else None
        return {
            "ok": current is not None,
            "key": symbol,
            "label": label,
            "value": current,
            "change_pct": change_pct,
            "kind": kind,
            "date": None,
            "source": "Yahoo Finance Chart API",
            "source_url": f"https://finance.yahoo.com/quote/{symbol}",
        }
    except Exception:
        return {
            "ok": False,
            "key": symbol,
            "label": label,
            "value": None,
            "change_pct": None,
            "kind": kind,
            "date": None,
            "source": "Yahoo Finance Chart API nicht erreichbar",
            "source_url": f"https://finance.yahoo.com/quote/{symbol}",
        }


def fetch_macro_quote(meta: dict[str, Any]) -> dict[str, Any]:
    fred_id = meta.get("fred_id")
    if fred_id:
        fred = fetch_fred_quote(fred_id, meta["label"], meta["kind"])
        if fred.get("ok"):
            return fred
    yahoo = fetch_yahoo_quote(meta["symbol"], meta["label"], meta["kind"])
    if yahoo.get("ok"):
        return yahoo
    stooq = fetch_stooq_quote(meta.get("stooq_symbol") or meta["symbol"], meta["label"], meta["kind"])
    if stooq.get("ok"):
        stooq["source"] = "Stooq Fallback"
        return stooq
    yahoo["source"] = "Yahoo/Stooq nicht erreichbar"
    return yahoo


def fetch_macro_quotes() -> dict[str, dict[str, Any]]:
    return {
        key: fetch_macro_quote(meta)
        for key, meta in MACRO_QUOTES.items()
    }


def fetch_cpi() -> dict[str, Any]:
    current_year = datetime.now(timezone.utc).year
    payload = {
        "seriesid": ["CUUR0000SA0"],
        "startyear": str(current_year - 2),
        "endyear": str(current_year),
        "calculations": True,
    }
    data = _post_json(BLS_API_URL, payload)
    try:
        rows = data["Results"]["series"][0]["data"]
        latest = rows[0]
        value = safe_float(latest.get("value"), None)
        period = latest.get("periodName") or latest.get("period")
        year = latest.get("year")
        yoy = safe_float((latest.get("calculations") or {}).get("pct_changes", {}).get("12"), None)
        if yoy is None and len(rows) >= 13 and value is not None:
            old = safe_float(rows[12].get("value"), None)
            if old not in (None, 0):
                yoy = (value - old) / old * 100
        return {
            "ok": value is not None,
            "label": "US CPI",
            "value": value,
            "yoy_pct": yoy,
            "period": f"{period} {year}".strip(),
            "source": "BLS public API",
            "source_url": "https://www.bls.gov/cpi/",
        }
    except Exception:
        return {
            "ok": False,
            "label": "US CPI",
            "value": None,
            "yoy_pct": None,
            "period": "n/a",
            "source": "BLS public API nicht erreichbar",
            "source_url": "https://www.bls.gov/cpi/",
        }


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _published_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def fetch_geopolitical_news(max_items_per_feed: int = 5, max_total: int = 18) -> list[dict[str, Any]]:
    try:
        import feedparser
    except Exception:
        return [{"source": "System", "title": "feedparser ist nicht installiert.", "published": "", "link": "", "risk_score": 0}]

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, url in GEOPOLITICAL_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in list(getattr(feed, "entries", []) or [])[:max_items_per_feed]:
                title = _clean_text(entry.get("title", "Ohne Titel"))
                summary = _clean_text(entry.get("summary", ""))
                link = entry.get("link", "") or ""
                dedupe = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
                if not dedupe or dedupe in seen:
                    continue
                seen.add(dedupe)
                text = f"{title} {summary}".lower()
                risk_score = sum(1 for word in GEOPOLITICAL_RISK_WORDS if word in text)
                dt = _published_datetime(entry)
                items.append({
                    "source": source,
                    "title": title,
                    "summary": summary[:280],
                    "published": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                    "published_ts": dt.timestamp() if dt else 0.0,
                    "link": link,
                    "risk_score": risk_score,
                })
        except Exception as exc:
            items.append({"source": source, "title": f"Feed konnte nicht geladen werden: {exc}", "published": "", "link": "", "risk_score": 0, "published_ts": 0.0})
    items.sort(key=lambda x: (float(x.get("risk_score") or 0), float(x.get("published_ts") or 0)), reverse=True)
    return items[:max_total]


def _status_from_quote(key: str, quote: dict[str, Any]) -> tuple[str, str]:
    value = safe_float(quote.get("value"), None)
    change = safe_float(quote.get("change_pct"), None)
    if value is None:
        return "⚪ n/a", "Quelle nicht erreichbar"
    if key in {"wti_oil", "brent_oil"}:
        if change is not None and change > 3:
            return "🔴 Oil shock risk", "Öl steigt stark; Inflation/Risk-off beobachten"
        if change is not None and change < -2:
            return "🟢 Easing", "Öl fällt; Makro-Druck nimmt ab"
        return "🟡 Stable", "Ölpreis ohne extremes Tagesrisiko"
    if key in {"us_2y", "us_10y"}:
        if change is not None and change > 1:
            return "🔴 Yield pressure", "Renditen steigen; Growth/Crypto Gegenwind"
        if change is not None and change < -1:
            return "🟢 Falling", "Renditen fallen; Liquiditätsbild freundlicher"
        return "🟡 Watch", "Renditen stabil, aber relevant"
    if key == "dxy":
        if change is not None and change > 0.6:
            return "🔴 Dollar stronger", "Starker Dollar belastet Risk Assets"
        if change is not None and change < -0.4:
            return "🟢 Dollar softer", "Schwächerer Dollar stützt Risk Assets"
        return "🟡 Neutral", "Dollar ohne klares Signal"
    return "🟡 Watch", "beobachten"


def macro_rows(quotes: dict[str, dict[str, Any]], cpi: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in ("wti_oil", "brent_oil", "us_2y", "us_10y", "dxy"):
        quote = quotes.get(key, {})
        status, reading = _status_from_quote(key, quote)
        kind = quote.get("kind")
        value = quote.get("value")
        if kind == "usd":
            value_text = fmt_usd(value)
        elif kind == "pct":
            value_text = "n/a" if value is None else f"{float(value):.2f}%"
        else:
            value_text = "n/a" if value is None else f"{float(value):.2f}"
        rows.append({
            "Layer": quote.get("label", key),
            "Wert": value_text,
            "Status": status,
            "Lesart": reading,
            "Quelle": quote.get("source", "n/a"),
        })

    yoy = safe_float(cpi.get("yoy_pct"), None)
    if yoy is None:
        status = "⚪ n/a"
        reading = "Inflationsdaten nicht erreichbar"
    elif yoy > 3.5:
        status = "🔴 Sticky inflation"
        reading = "Fed bleibt tendenziell restriktiver"
    elif yoy < 2.7:
        status = "🟢 Disinflation"
        reading = "Makro-Rückenwind für Risk Assets"
    else:
        status = "🟡 Watch"
        reading = "Inflation moderat, aber Fed-relevant"
    rows.append({
        "Layer": "US CPI YoY",
        "Wert": "n/a" if yoy is None else fmt_pct(yoy, 1),
        "Status": status,
        "Lesart": reading,
        "Quelle": cpi.get("source", "BLS"),
    })
    return rows


def geopolitical_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    risk_hits = sum(1 for item in items if safe_float(item.get("risk_score"), 0) > 0)
    if risk_hits >= 7:
        status = "🔴 Elevated"
        reading = "Viele geopolitische Risiko-Schlagworte in aktuellen News."
    elif risk_hits >= 3:
        status = "🟡 Watch"
        reading = "Geopolitisches Risiko vorhanden, aber nicht dominant."
    else:
        status = "🟢 Calm"
        reading = "Keine starke Häufung geopolitischer Risiko-Schlagworte."
    return {"status": status, "risk_hits": risk_hits, "reading": reading}


def macro_score(rows: list[dict[str, str]], geo: dict[str, Any]) -> tuple[int, str]:
    score = 50
    joined = " ".join(f"{row.get('Status','')} {row.get('Lesart','')}" for row in rows).lower()
    score -= joined.count("🔴") * 10
    score += joined.count("🟢") * 7
    if str(geo.get("status", "")).startswith("🔴"):
        score -= 12
    elif str(geo.get("status", "")).startswith("🟢"):
        score += 5
    score = max(0, min(100, score))
    if score >= 65:
        label = "Macro Rückenwind"
    elif score >= 45:
        label = "Macro neutral / beobachten"
    else:
        label = "Macro Gegenwind"
    return score, label


def build_macro_monitor() -> dict[str, Any]:
    quotes = fetch_macro_quotes()
    cpi = fetch_cpi()
    news = fetch_geopolitical_news()
    rows = macro_rows(quotes, cpi)
    geo = geopolitical_summary(news)
    score, label = macro_score(rows, geo)
    return {
        "score": score,
        "label": label,
        "rows": rows,
        "geopolitics": geo,
        "news": news,
        "fedwatch_url": CME_FEDWATCH_URL,
    }
