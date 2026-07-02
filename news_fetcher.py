from __future__ import annotations

from typing import Any

POSITIVE_KEYWORDS = [
    "etf", "rwa", "tokenized", "tokenised", "tokenization", "tokenisation", "moneygram", "validator",
    "alpenglow", "agave", "firedancer", "stablecoin", "institutional", "partnership", "adoption", "japan",
    "bitflyer", "micron", "treasury", "blackrock", "franklin", "securitize", "upgrade", "growth", "launch", "listing",
]
NEGATIVE_KEYWORDS = ["outage", "downtime", "hack", "exploit", "sec", "lawsuit", "delist", "delay", "bug", "halted", "congestion", "failed", "risk", "crackdown", "investigation"]

NEWS_FEEDS = {
    "Google News: Solana RWA": "https://news.google.com/rss/search?q=Solana+RWA+tokenized+assets",
    "Google News: Solana ETF": "https://news.google.com/rss/search?q=Solana+ETF",
    "Google News: Solana Alpenglow": "https://news.google.com/rss/search?q=Solana+Alpenglow",
    "Google News: Solana MoneyGram": "https://news.google.com/rss/search?q=Solana+MoneyGram",
    "Reddit r/solana": "https://www.reddit.com/r/solana/.rss",
    "Reddit r/CryptoCurrency Solana": "https://www.reddit.com/r/CryptoCurrency/search.rss?q=Solana&restrict_sr=on&sort=new&t=week",
}


def classify_news(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    pos = sum(1 for w in POSITIVE_KEYWORDS if w in text)
    neg = sum(1 for w in NEGATIVE_KEYWORDS if w in text)
    if neg > pos:
        return "🔴 Risiko"
    if pos:
        return "🟢 Positiv"
    return "🟡 Neutral"


def fetch_news(max_items_per_feed: int = 4) -> list[dict[str, Any]]:
    try:
        import feedparser
    except Exception:
        return [{"source": "System", "title": "feedparser ist nicht installiert.", "link": "", "published": "", "classification": "🟡 Neutral"}]
    items: list[dict[str, Any]] = []
    for source, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items_per_feed]:
                title = entry.get("title", "Ohne Titel")
                summary = entry.get("summary", "")
                items.append({
                    "source": source,
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "classification": classify_news(title, summary),
                })
        except Exception as exc:
            items.append({"source": source, "title": f"Feed konnte nicht geladen werden: {exc}", "link": "", "published": "", "classification": "🟡 Neutral"})
    return items
