{\rtf1\ansi\ansicpg1252\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import feedparser\
from datetime import datetime\
\
NEWS_FEEDS = \{\
    "Google News: Solana RWA": "https://news.google.com/rss/search?q=Solana+RWA+tokenized+assets",\
    "Google News: Solana ETF": "https://news.google.com/rss/search?q=Solana+ETF",\
    "Google News: Solana Alpenglow": "https://news.google.com/rss/search?q=Solana+Alpenglow",\
    "Google News: Solana MoneyGram": "https://news.google.com/rss/search?q=Solana+MoneyGram",\
    "Reddit r/solana": "https://www.reddit.com/r/solana/.rss",\
    "Reddit r/CryptoCurrency Solana": "https://www.reddit.com/r/CryptoCurrency/search.rss?q=Solana&restrict_sr=on&sort=new&t=week",\
\}\
\
POSITIVE_KEYWORDS = [\
    "etf", "rwa", "tokenized", "tokenisation", "tokenization",\
    "moneygram", "validator", "alpenglow", "agave", "firedancer",\
    "stablecoin", "institutional", "partnership", "adoption",\
    "japan", "bitflyer", "micron", "treasury", "blackrock",\
    "franklin", "securitize"\
]\
\
NEGATIVE_KEYWORDS = [\
    "outage", "downtime", "hack", "exploit", "sec", "lawsuit",\
    "delist", "delay", "bug", "halted", "congestion",\
    "failed", "risk", "regulatory crackdown"\
]\
\
\
def classify_news(title: str, summary: str = "") -> str:\
    text = f"\{title\} \{summary\}".lower()\
\
    positive_hits = sum(1 for word in POSITIVE_KEYWORDS if word in text)\
    negative_hits = sum(1 for word in NEGATIVE_KEYWORDS if word in text)\
\
    if negative_hits > positive_hits:\
        return "\uc0\u55357 \u56628  Risiko"\
    if positive_hits > 0:\
        return "\uc0\u55357 \u57314  Positiv"\
    return "\uc0\u55357 \u57313  Neutral"\
\
\
def fetch_news(max_items_per_feed: int = 5):\
    items = []\
\
    for source, url in NEWS_FEEDS.items():\
        feed = feedparser.parse(url)\
\
        for entry in feed.entries[:max_items_per_feed]:\
            title = entry.get("title", "Ohne Titel")\
            link = entry.get("link", "")\
            summary = entry.get("summary", "")\
            published = entry.get("published", "")\
\
            items.append(\{\
                "source": source,\
                "title": title,\
                "link": link,\
                "published": published,\
                "classification": classify_news(title, summary),\
            \})\
\
    return items}