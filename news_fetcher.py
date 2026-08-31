from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

POSITIVE_KEYWORDS = [
    "etf", "rwa", "tokenized", "tokenised", "tokenization", "tokenisation", "moneygram",
    "validator", "alpenglow", "agave", "firedancer", "stablecoin", "institutional",
    "partnership", "adoption", "japan", "bitflyer", "treasury", "blackrock", "franklin",
    "securitize", "upgrade", "growth", "launch", "listing", "jito", "jupiter", "paypal",
    "visa", "stripe", "helius", "anza", "breakpoint", "throughput", "mainnet", "record",
]
NEGATIVE_KEYWORDS = [
    "outage", "downtime", "hack", "exploit", "sec", "lawsuit", "delist", "delay", "bug",
    "halted", "congestion", "failed", "risk", "crackdown", "investigation", "phishing",
    "scam", "vulnerability", "attack", "drain", "rug", "fraud", "sanction",
]

# Mostly Google News RSS because it is stable, broad and does not require API keys.
# Queries are deliberately split into research themes so the dashboard does not return only one article.
NEWS_FEEDS: dict[str, str] = {
    "Google News: Solana Top": "https://news.google.com/rss/search?q=Solana%20crypto%20when:7d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Solana ETF": "https://news.google.com/rss/search?q=Solana%20ETF%20OR%20SOL%20ETF%20when:14d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Solana RWA": "https://news.google.com/rss/search?q=Solana%20RWA%20OR%20tokenized%20assets%20Solana%20when:30d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Solana DeFi": "https://news.google.com/rss/search?q=Solana%20DeFi%20Jupiter%20Jito%20Raydium%20when:14d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Solana Tech": "https://news.google.com/rss/search?q=Solana%20Firedancer%20OR%20Alpenglow%20OR%20Anza%20when:30d&hl=en-US&gl=US&ceid=US:en",
    "Google News: SOL Market": "https://news.google.com/rss/search?q=SOL%20price%20Solana%20market%20when:7d&hl=en-US&gl=US&ceid=US:en",
    "Google News: Stablecoins Solana": "https://news.google.com/rss/search?q=Solana%20stablecoins%20USDC%20PayPal%20when:30d&hl=en-US&gl=US&ceid=US:en",
    "Reddit r/solana": "https://www.reddit.com/r/solana/.rss",
    "Reddit r/CryptoCurrency Solana": "https://www.reddit.com/r/CryptoCurrency/search.rss?q=Solana&restrict_sr=on&sort=new&t=week",
}

KRYPTOVERGLEICH_SOLANA_NEWS_URL = "https://www.kryptovergleich.de/kryptowaehrungen/solana/news"
HTTP_HEADERS = {"User-Agent": "solana-research-terminal/5.3", "Accept": "text/html,application/xhtml+xml"}
REQUEST_TIMEOUT = 20

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ETF / Institutional": ["etf", "institution", "blackrock", "franklin", "treasury", "sec"],
    "RWA / Stablecoins": ["rwa", "tokenized", "tokenised", "stablecoin", "usdc", "paypal", "visa", "moneygram"],
    "DeFi / Ecosystem": ["defi", "jito", "jupiter", "raydium", "orca", "drift", "helium", "depin"],
    "Tech / Network": ["firedancer", "alpenglow", "anza", "validator", "throughput", "upgrade", "mainnet", "agave"],
    "Market / Price": ["price", "rally", "market", "trading", "funding", "futures", "open interest", "liquidation"],
    "Risk": NEGATIVE_KEYWORDS,
}

CATEGORY_IMPACT_WEIGHTS = {
    "ETF / Institutional": 1.35,
    "RWA / Stablecoins": 1.25,
    "Tech / Network": 1.25,
    "Risk": 1.35,
    "DeFi / Ecosystem": 1.10,
    "Market / Price": 0.95,
    "Allgemein": 0.75,
    "System": 0.0,
}


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_title(title: str) -> str:
    title = _clean_text(title).lower()
    title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)  # strip publisher suffix from Google News titles
    title = re.sub(r"[^a-z0-9äöüß]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _published_datetime(entry: Any) -> datetime | None:
    # feedparser may expose both parsed tuples and raw strings.
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


def _format_published(dt: datetime | None, fallback: str = "") -> str:
    if dt is None:
        return fallback or ""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def classify_news(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    pos = sum(1 for w in POSITIVE_KEYWORDS if w in text)
    neg = sum(1 for w in NEGATIVE_KEYWORDS if w in text)
    if neg > pos:
        return "🔴 Risiko"
    if pos:
        return "🟢 Positiv"
    return "🟡 Neutral"


def categorize_news(title: str, summary: str = "", source: str = "") -> str:
    text = f"{title} {summary} {source}".lower()
    best_category = "Allgemein"
    best_hits = 0
    for category, words in CATEGORY_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > best_hits:
            best_category = category
            best_hits = hits
    return best_category


def _freshness_weight(published_ts: Any) -> float:
    ts = 0.0
    try:
        ts = float(published_ts or 0.0)
    except Exception:
        return 0.55
    if ts <= 0:
        return 0.55
    age_hours = max((datetime.now(timezone.utc).timestamp() - ts) / 3600, 0)
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.80
    if age_hours <= 168:
        return 0.60
    return 0.40


def _source_weight(source: str) -> float:
    source_l = source.lower()
    if "kryptovergleich" in source_l:
        return 1.35
    if "google news" in source_l:
        return 1.0
    if "reddit" in source_l:
        return 0.55
    return 0.85


def _impact_points(item: dict[str, Any]) -> float:
    classification = str(item.get("classification") or "")
    if "Positiv" in classification:
        direction = 1.0
    elif "Risiko" in classification:
        direction = -1.15
    else:
        direction = 0.0

    category = str(item.get("category") or "Allgemein")
    source = str(item.get("source") or "")
    magnitude = CATEGORY_IMPACT_WEIGHTS.get(category, 0.8)
    return direction * magnitude * _source_weight(source) * _freshness_weight(item.get("published_ts"))


def build_news_impact_report(items: list[dict[str, Any]], max_reasons: int = 3) -> dict[str, Any]:
    relevant = [item for item in items if str(item.get("category") or "") != "System"]
    if not relevant:
        return {
            "score": 50,
            "label": "neutral",
            "positive_count": 0,
            "risk_count": 0,
            "net_impact": 0.0,
            "reasons_positive": [],
            "reasons_risk": [],
        }

    scored = [(item, _impact_points(item)) for item in relevant]
    net = sum(points for _, points in scored)
    score = round(max(10, min(90, 50 + net * 4)))

    if score >= 68:
        label = "News Rückenwind"
    elif score >= 55:
        label = "leicht positiv"
    elif score <= 32:
        label = "News Risiko"
    elif score <= 45:
        label = "leicht negativ"
    else:
        label = "neutral"

    positives = sorted(((item, points) for item, points in scored if points > 0), key=lambda row: row[1], reverse=True)
    risks = sorted(((item, points) for item, points in scored if points < 0), key=lambda row: row[1])

    return {
        "score": score,
        "label": label,
        "positive_count": sum(1 for item in relevant if item.get("classification") == "🟢 Positiv"),
        "risk_count": sum(1 for item in relevant if item.get("classification") == "🔴 Risiko"),
        "net_impact": round(net, 2),
        "reasons_positive": [
            f"{item.get('category', 'Allgemein')}: {item.get('title', 'Ohne Titel')}"
            for item, _ in positives[:max_reasons]
        ],
        "reasons_risk": [
            f"{item.get('category', 'Allgemein')}: {item.get('title', 'Ohne Titel')}"
            for item, _ in risks[:max_reasons]
        ],
    }


def _json_ld_objects(page_html: str) -> list[Any]:
    objects: list[Any] = []
    pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for match in re.finditer(pattern, page_html, flags=re.IGNORECASE | re.DOTALL):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except Exception:
            continue
    return objects


def _iter_news_articles(value: Any) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            articles.extend(_iter_news_articles(item))
        return articles
    if not isinstance(value, dict):
        return articles

    typ = value.get("@type")
    if typ == "NewsArticle" or (isinstance(typ, list) and "NewsArticle" in typ):
        articles.append(value)

    main_entity = value.get("mainEntity")
    if isinstance(main_entity, dict):
        articles.extend(_iter_news_articles(main_entity))

    item_list = value.get("itemListElement")
    if isinstance(item_list, list):
        for item in item_list:
            articles.extend(_iter_news_articles(item))
    return articles


def fetch_kryptovergleich_news(max_items: int = 10) -> list[dict[str, Any]]:
    try:
        response = requests.get(KRYPTOVERGLEICH_SOLANA_NEWS_URL, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:
        return [{
            "source": "Kryptovergleich: Solana News",
            "title": f"Kryptovergleich konnte nicht geladen werden: {exc}",
            "link": KRYPTOVERGLEICH_SOLANA_NEWS_URL,
            "published": "",
            "published_ts": 0.0,
            "summary": "",
            "category": "System",
            "classification": "🟡 Neutral",
        }]

    items: list[dict[str, Any]] = []
    for obj in _json_ld_objects(response.text):
        for article in _iter_news_articles(obj):
            title = _clean_text(article.get("headline") or article.get("name") or "Ohne Titel")
            summary = _clean_text(article.get("description") or "")
            link = str(article.get("url") or KRYPTOVERGLEICH_SOLANA_NEWS_URL)
            published_dt = _parse_iso_datetime(article.get("datePublished") or article.get("dateModified"))
            publisher = article.get("publisher") or {}
            publisher_name = publisher.get("name") if isinstance(publisher, dict) else ""
            source = "Kryptovergleich: Solana News"
            if publisher_name:
                source = f"{source} · {publisher_name}"
            items.append({
                "source": source,
                "title": title,
                "link": link,
                "published": _format_published(published_dt),
                "published_ts": published_dt.timestamp() if published_dt else 0.0,
                "summary": summary[:420],
                "category": categorize_news(title, summary, source),
                "classification": classify_news(title, summary),
            })

    items.sort(key=lambda x: float(x.get("published_ts") or 0.0), reverse=True)
    return items[:max_items]


def fetch_news(max_items_per_feed: int = 8, max_total: int = 40) -> list[dict[str, Any]]:
    try:
        import feedparser
    except Exception:
        return [{
            "source": "System",
            "title": "feedparser ist nicht installiert.",
            "link": "",
            "published": "",
            "published_ts": 0.0,
            "summary": "",
            "category": "System",
            "classification": "🟡 Neutral",
        }]

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in fetch_kryptovergleich_news(max_items=10):
        norm = _normalize_title(str(item.get("title") or ""))
        dedupe_key = norm or str(item.get("link") or "")
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(item)

    for source, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            entries = list(getattr(feed, "entries", []) or [])
            for entry in entries[:max_items_per_feed]:
                title = _clean_text(entry.get("title", "Ohne Titel"))
                summary = _clean_text(entry.get("summary", ""))
                link = entry.get("link", "") or ""
                dt = _published_datetime(entry)
                norm = _normalize_title(title)
                dedupe_key = norm or link
                if not dedupe_key or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                classification = classify_news(title, summary)
                items.append({
                    "source": source,
                    "title": title,
                    "link": link,
                    "published": _format_published(dt, entry.get("published", "")),
                    "published_ts": dt.timestamp() if dt else 0.0,
                    "summary": summary[:420],
                    "category": categorize_news(title, summary, source),
                    "classification": classification,
                })
        except Exception as exc:
            items.append({
                "source": source,
                "title": f"Feed konnte nicht geladen werden: {exc}",
                "link": "",
                "published": "",
                "published_ts": 0.0,
                "summary": "",
                "category": "System",
                "classification": "🟡 Neutral",
            })

    # Newest first; unknown dates go last.
    items.sort(key=lambda x: float(x.get("published_ts") or 0.0), reverse=True)
    return items[:max_total]
