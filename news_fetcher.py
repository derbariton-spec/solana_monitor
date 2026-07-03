from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

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

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ETF / Institutional": ["etf", "institution", "blackrock", "franklin", "treasury", "sec"],
    "RWA / Stablecoins": ["rwa", "tokenized", "tokenised", "stablecoin", "usdc", "paypal", "visa", "moneygram"],
    "DeFi / Ecosystem": ["defi", "jito", "jupiter", "raydium", "orca", "drift", "helium", "depin"],
    "Tech / Network": ["firedancer", "alpenglow", "anza", "validator", "throughput", "upgrade", "mainnet", "agave"],
    "Market / Price": ["price", "rally", "market", "trading", "funding", "futures", "open interest", "liquidation"],
    "Risk": NEGATIVE_KEYWORDS,
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
