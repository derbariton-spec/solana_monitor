from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from config import APP_TITLE, WATCHLIST_JSON
from score import LABELS, WEIGHTS, compute_fundamental_score, interpretation_text, traffic_light
from storage import load_history

load_dotenv()

SOLANA_LOGO_URL = "https://cryptologos.cc/logos/solana-sol-logo.png"

st.set_page_config(page_title=APP_TITLE, page_icon="🟣", layout="wide")


# ------------------------------------------------------------
# Formatierung
# ------------------------------------------------------------

def fmt_usd(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"

    value = float(value)

    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f} Mrd. $".replace(",", "X").replace(".", ",").replace("X", ".")

    if abs(value) >= 1e6:
        return f"{value / 1e6:,.2f} Mio. $".replace(",", "X").replace(".", ",").replace("X", ".")

    return f"{value:,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(value, decimals=2) -> str:
    if value is None or pd.isna(value):
        return "n/a"

    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value, decimals=2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):+,.{decimals}f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_datetime_utc(dt) -> str:
    if dt is None:
        return "n/a"
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return "n/a"


def safe_float(value, fallback=0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(fallback)
        return float(value)
    except Exception:
        return float(fallback)


# ------------------------------------------------------------
# Solana Logo / Header
# ------------------------------------------------------------


def render_header():
    """Stabiler Header ohne HTML, damit kein CSS/Text sichtbar gerendert wird."""
    logo_col, text_col = st.columns([0.08, 0.92])

    with logo_col:
        st.image(SOLANA_LOGO_URL, width=58)

    with text_col:
        st.title("Solana Fundamental Monitor")
        st.caption(
            "Live-Markt, Fundamentaldaten, News und Investmentthese – "
            "persönliches Dashboard für Solana als Finanzinfrastruktur."
        )


@st.cache_data(ttl=30)
def fetch_live_market_data() -> dict:
    """
    Lädt Live-Marktdaten von CoinGecko.
    Der Cache läuft nur 30 Sekunden, damit der Kurs quasi live bleibt,
    ohne die API bei jedem Streamlit-Rerun zu überlasten.
    """
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=solana,jito-staked-sol,bitcoin"
        "&vs_currencies=usd,eur"
        "&include_24hr_change=true"
        "&include_market_cap=true"
        "&include_24hr_vol=true"
    )

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "solana-fundamental-monitor/2.0"},
        )
        response.raise_for_status()
        data = response.json()

        sol = data.get("solana", {})
        jitosol = data.get("jito-staked-sol", {})
        btc = data.get("bitcoin", {})

        return {
            "ok": True,
            "error": None,
            "last_update": datetime.now(timezone.utc),
            "sol_usd_live": sol.get("usd"),
            "sol_eur_live": sol.get("eur"),
            "sol_24h_change": sol.get("usd_24h_change"),
            "sol_market_cap": sol.get("usd_market_cap"),
            "sol_volume_24h": sol.get("usd_24h_vol"),
            "jitosol_usd_live": jitosol.get("usd"),
            "jitosol_eur_live": jitosol.get("eur"),
            "jitosol_24h_change": jitosol.get("usd_24h_change"),
            "btc_usd_live": btc.get("usd"),
            "btc_eur_live": btc.get("eur"),
            "btc_24h_change": btc.get("usd_24h_change"),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "last_update": datetime.now(timezone.utc),
        }


def build_thesis_commentary(result: dict, latest, live: dict, past_available: bool) -> str:
    """Einfache regelbasierte Tages-Einschätzung ohne externen KI-Key."""
    status = result.get("status", "neutral")
    score = safe_float(result.get("score"), 50)
    sol_change = live.get("sol_24h_change")
    rwa = safe_float(latest.get("rwa_usd"), 0)
    stable = safe_float(latest.get("stablecoins_usd"), 0)
    tvl = safe_float(latest.get("tvl_usd"), 0)

    parts = []
    if status == "intakt" or score >= 70:
        parts.append("Die Investmentthese wirkt aktuell intakt.")
    elif status == "geschwaecht" or score < 40:
        parts.append("Die Investmentthese wirkt aktuell geschwächt und sollte genauer geprüft werden.")
    else:
        parts.append("Die Investmentthese wirkt aktuell neutral, weil noch nicht genug Verlauf vorliegt oder die Signale gemischt sind.")

    if rwa >= 1_000_000_000:
        parts.append("RWA liegt weiterhin im Milliardenbereich und bleibt damit ein zentraler Baustein der Solana-Finanzinfrastruktur-These.")
    if stable >= 10_000_000_000:
        parts.append("Die Stablecoin-Basis ist groß genug, um echte Finanzanwendungen zu tragen.")
    if tvl >= 4_000_000_000:
        parts.append("Das TVL bleibt auf relevantem Niveau, auch wenn kurzfristige Schwankungen normal sind.")
    if sol_change is not None:
        if sol_change > 3:
            parts.append("Der Live-Kurs zeigt kurzfristig relative Stärke.")
        elif sol_change < -3:
            parts.append("Der Live-Kurs steht kurzfristig unter Druck; das ist aber nicht automatisch eine fundamentale Verschlechterung.")

    if not past_available:
        parts.append("Die 30-Tage-Ampel wird aussagekräftiger, sobald mehr tägliche Historie gesammelt wurde.")

    return " ".join(parts)


def pct_delta(latest, prev, key):
    if prev is None:
        return None

    if pd.isna(prev.get(key)) or pd.isna(latest.get(key)):
        return None

    if float(prev.get(key)) == 0:
        return None

    return (float(latest.get(key)) - float(prev.get(key))) / float(prev.get(key)) * 100


def row_to_dict(row) -> dict | None:
    if row is None:
        return None

    result = {}

    for k, v in row.to_dict().items():
        if pd.isna(v):
            result[k] = None
        elif isinstance(v, (int, float)):
            result[k] = float(v)
        else:
            result[k] = v

    return result


# ------------------------------------------------------------
# Watchlist
# ------------------------------------------------------------

def load_watchlist() -> list[dict]:
    path = Path(WATCHLIST_JSON)

    if not path.exists():
        return []

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


# ------------------------------------------------------------
# News / Reddit Feeds
# ------------------------------------------------------------

NEWS_FEEDS = {
    "Google News: Solana RWA": "https://news.google.com/rss/search?q=Solana+RWA+tokenized+assets",
    "Google News: Solana ETF": "https://news.google.com/rss/search?q=Solana+ETF",
    "Google News: Solana Alpenglow": "https://news.google.com/rss/search?q=Solana+Alpenglow",
    "Google News: Solana Agave": "https://news.google.com/rss/search?q=Solana+Agave+upgrade",
    "Google News: Solana MoneyGram": "https://news.google.com/rss/search?q=Solana+MoneyGram",
    "Google News: Solana tokenized stocks": "https://news.google.com/rss/search?q=Solana+tokenized+stocks",
    "Reddit r/solana": "https://www.reddit.com/r/solana/.rss",
    "Reddit r/CryptoCurrency Solana": "https://www.reddit.com/r/CryptoCurrency/search.rss?q=Solana&restrict_sr=on&sort=new&t=week",
}

POSITIVE_KEYWORDS = [
    "etf",
    "rwa",
    "tokenized",
    "tokenised",
    "tokenization",
    "tokenisation",
    "moneygram",
    "validator",
    "alpenglow",
    "agave",
    "firedancer",
    "stablecoin",
    "institutional",
    "partnership",
    "adoption",
    "japan",
    "bitflyer",
    "micron",
    "treasury",
    "blackrock",
    "franklin",
    "securitize",
    "upgrade",
    "growth",
    "launch",
    "listing",
]

NEGATIVE_KEYWORDS = [
    "outage",
    "downtime",
    "hack",
    "exploit",
    "sec",
    "lawsuit",
    "delist",
    "delay",
    "bug",
    "halted",
    "congestion",
    "failed",
    "risk",
    "crackdown",
    "investigation",
]


def classify_news(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()

    positive_hits = sum(1 for word in POSITIVE_KEYWORDS if word in text)
    negative_hits = sum(1 for word in NEGATIVE_KEYWORDS if word in text)

    if negative_hits > positive_hits:
        return "🔴 Risiko"

    if positive_hits > 0:
        return "🟢 Positiv"

    return "🟡 Neutral"


def fetch_news(max_items_per_feed: int = 4) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        return [{
            "source": "System",
            "title": "feedparser ist nicht installiert. Bitte im Terminal ausführen: pip install feedparser",
            "link": "",
            "published": "",
            "classification": "🟡 Neutral",
        }]

    items = []

    for source, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:max_items_per_feed]:
                title = entry.get("title", "Ohne Titel")
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                published = entry.get("published", "")

                items.append({
                    "source": source,
                    "title": title,
                    "link": link,
                    "published": published,
                    "classification": classify_news(title, summary),
                })

        except Exception as e:
            items.append({
                "source": source,
                "title": f"Feed konnte nicht geladen werden: {e}",
                "link": "",
                "published": "",
                "classification": "🟡 Neutral",
            })

    return items


# ------------------------------------------------------------
# Daten laden
# ------------------------------------------------------------

df = load_history(days=365)

render_header()

if df.empty:
    st.warning(
        "Noch keine Daten vorhanden. Starte zuerst `python3 fetch_data.py`. "
        "Ohne Supabase wird automatisch `data/solana_fundamentals.csv` genutzt."
    )
    st.stop()

# sicherstellen, dass snapshot_date als Datum erkannt wird
if "snapshot_date" in df.columns:
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])

latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else None

# 30-Tage-Vergleich
past = None
target = latest["snapshot_date"] - pd.Timedelta(days=30)
past_candidates = df[df["snapshot_date"] <= target]

if not past_candidates.empty:
    past = past_candidates.iloc[-1]

current_dict = row_to_dict(latest)
past_dict = row_to_dict(past) if past is not None else None
result = compute_fundamental_score(current_dict, past_dict)

sol_usd = float(latest.get("sol_usd") or 0)
sol_btc = float(latest.get("sol_btc") or 0)

# Live-Marktdaten: unabhängig vom täglichen Fundamentaldaten-Snapshot
live = fetch_live_market_data()
sol_usd_live = safe_float(live.get("sol_usd_live"), sol_usd)
sol_eur_live = live.get("sol_eur_live")
sol_24h_change = live.get("sol_24h_change")
sol_market_cap_live = live.get("sol_market_cap")
sol_volume_24h_live = live.get("sol_volume_24h")
jitosol_usd_live = live.get("jitosol_usd_live")
jitosol_eur_live = live.get("jitosol_eur_live")
jitosol_24h_change = live.get("jitosol_24h_change")
btc_usd_live = live.get("btc_usd_live")
btc_eur_live = live.get("btc_eur_live")
btc_24h_change = live.get("btc_24h_change")
live_last_update = live.get("last_update")


# ------------------------------------------------------------
# Sidebar: Deine Position
# ------------------------------------------------------------

with st.sidebar:
    st.header("Deine Position")

    jitosol_amount = st.number_input(
        "JitoSOL Bestand",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.5f"
    )

    sol_equivalent = st.number_input(
        "≈ SOL Gegenwert",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f"
    )

    avg_entry_jitosol = st.number_input(
        "Ø Einstieg JitoSOL USD",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f"
    )

    historical_sol_entry = st.number_input(
        "Historischer SOL-Einstieg USD",
        min_value=0.0,
        value=0.0,
        step=1.0,
        format="%.2f"
    )

    # JitoSOL-Preis bevorzugt live von CoinGecko; Fallback über SOL/USD × JitoSOL/SOL-Verhältnis
    jitosol_sol_ratio = sol_equivalent / jitosol_amount if jitosol_amount else 0
    if jitosol_usd_live:
        current_jitosol_price = float(jitosol_usd_live)
    else:
        current_jitosol_price = jitosol_sol_ratio * sol_usd_live

    value_now = jitosol_amount * current_jitosol_price
    cost_basis = jitosol_amount * avg_entry_jitosol
    pnl = value_now - cost_basis
    pnl_pct = (value_now / cost_basis - 1) * 100 if cost_basis else 0

    st.metric("Aktueller JitoSOL Preis", fmt_usd(current_jitosol_price))
    st.caption(f"1 JitoSOL ≈ {jitosol_sol_ratio:.4f} SOL")

    st.metric("Aktueller Wert", fmt_usd(value_now))
    st.caption(f"{jitosol_amount:.5f} JitoSOL × {current_jitosol_price:.2f} USD")
    st.caption(f"≈ {sol_equivalent:.2f} SOL")

    st.metric(
        "Buchgewinn/-verlust",
        fmt_usd(pnl),
        delta=f"{pnl_pct:+.1f}%"
    )

    st.divider()

    st.write("**Einstandsdaten**")
    st.write(f"JitoSOL-Einstieg: **{avg_entry_jitosol:.2f} USD**")
    st.write(f"Historischer SOL-Einstieg: **{historical_sol_entry:.2f} USD**")

    st.divider()

    st.caption(
        "Keine Anlageberatung. Der Monitor soll deine These prüfen, "
        "nicht Kurzfrist-Trades auslösen."
    )


# ------------------------------------------------------------
# Kopfbereich
# ------------------------------------------------------------

score = float(result["score"])
status_icon = "🟢" if result["status"] == "intakt" else "🔴" if result["status"] == "geschwaecht" else "🟡"

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Thesis Status", f"{status_icon} {result['status'].capitalize()}")
c2.metric("Fundamental Score", f"{score:.0f}/100")
c3.metric(
    "SOL/USD Live",
    f"{sol_usd_live:.2f} $",
    None if sol_24h_change is None else fmt_pct(sol_24h_change) + " 24h"
)
c4.metric(
    "SOL/EUR Live",
    "n/a" if sol_eur_live is None else f"{float(sol_eur_live):.2f} €"
)
c5.metric(
    "SOL/BTC",
    f"{sol_btc:.6f}",
    None if prev is None else f"{pct_delta(latest, prev, 'sol_btc'):+.1f}%"
)

if live.get("error"):
    st.warning(f"Live-Marktdaten konnten nicht geladen werden: {live.get('error')}")
elif live_last_update:
    st.caption(f"Live-Kurs zuletzt abgefragt: {fmt_datetime_utc(live_last_update)}")

st.progress(max(0, min(int(score), 100)) / 100)
st.info(interpretation_text(result))
st.success(build_thesis_commentary(result, latest, live, past is not None))


# ------------------------------------------------------------
# Tabs
# ------------------------------------------------------------

fundamentals, market, thesis, news, history, raw = st.tabs([
    "Fundamentals",
    "Markt",
    "Investmentthese",
    "News",
    "Verlauf",
    "Rohdaten"
])


# ------------------------------------------------------------
# Tab: Fundamentals
# ------------------------------------------------------------

with fundamentals:
    st.subheader("Kernkennzahlen")

    a, b, c, d = st.columns(4)

    a.metric(
        "TVL USD",
        fmt_usd(latest.get("tvl_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'tvl_usd'):+.1f}%"
    )

    b.metric(
        "TVL in SOL",
        fmt_num(latest.get("tvl_sol"), 0),
        None if prev is None else f"{pct_delta(latest, prev, 'tvl_sol'):+.1f}%"
    )

    c.metric(
        "Stablecoins",
        fmt_usd(latest.get("stablecoins_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'stablecoins_usd'):+.1f}%"
    )

    d.metric(
        "RWA",
        fmt_usd(latest.get("rwa_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'rwa_usd'):+.1f}%"
    )

    e, f, g, h = st.columns(4)

    e.metric(
        "DEX Volumen 24h",
        fmt_usd(latest.get("dex_volume_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'dex_volume_usd'):+.1f}%"
    )

    f.metric(
        "Fees 24h",
        fmt_usd(latest.get("fees_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'fees_usd'):+.1f}%"
    )

    g.metric(
        "Revenue 24h",
        fmt_usd(latest.get("revenue_usd")),
        None if prev is None else f"{pct_delta(latest, prev, 'revenue_usd'):+.1f}%"
    )

    active = latest.get("active_addresses")
    h.metric("Active Addresses", "n/a" if pd.isna(active) else fmt_num(active, 0))

    st.subheader("30-Tage-Ampel")

    rows = []

    for key in WEIGHTS:
        growth = result["growth_pct"].get(key)

        rows.append({
            "Ampel": traffic_light(growth),
            "Kennzahl": LABELS.get(key, key),
            "30T": "Zu wenig Historie" if growth is None else f"{growth:+.1f}%",
            "Gewicht": f"{WEIGHTS[key] * 100:.0f}%"
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True
    )


# ------------------------------------------------------------
# Tab: Markt
# ------------------------------------------------------------

with market:
    st.subheader("Live-Markt")

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "SOL/USD Live",
        f"{sol_usd_live:.2f} $",
        None if sol_24h_change is None else fmt_pct(sol_24h_change) + " 24h"
    )

    m2.metric(
        "SOL/EUR Live",
        "n/a" if sol_eur_live is None else f"{float(sol_eur_live):.2f} €"
    )

    m3.metric(
        "JitoSOL/USD Live",
        "n/a" if jitosol_usd_live is None else f"{float(jitosol_usd_live):.2f} $",
        None if jitosol_24h_change is None else fmt_pct(jitosol_24h_change) + " 24h"
    )

    if jitosol_usd_live and sol_usd_live:
        jito_premium = (float(jitosol_usd_live) / float(sol_usd_live) - 1) * 100
        m4.metric("JitoSOL Premium", fmt_pct(jito_premium))
    else:
        m4.metric("JitoSOL Premium", "n/a")

    st.divider()

    x1, x2, x3, x4 = st.columns(4)

    x1.metric("SOL Market Cap", fmt_usd(sol_market_cap_live))
    x2.metric("SOL Volumen 24h", fmt_usd(sol_volume_24h_live))
    x3.metric(
        "BTC/USD Live",
        fmt_usd(btc_usd_live),
        None if btc_24h_change is None else fmt_pct(btc_24h_change) + " 24h"
    )
    x4.metric("SOL/BTC", f"{sol_btc:.6f}")

    btc_dom = latest.get("btc_dominance")
    st.metric(
        "BTC Dominanz (täglicher Snapshot)",
        "n/a" if pd.isna(btc_dom) else f"{float(btc_dom):.1f}%"
    )

    if live_last_update:
        st.caption(f"Live-Daten zuletzt abgefragt: {fmt_datetime_utc(live_last_update)}")

    st.caption(
        "SOL/BTC ist für deine These wichtig: Es zeigt, ob Solana relativ "
        "zu Bitcoin Stärke aufbaut. Der SOL/USD- und JitoSOL-Kurs oben ist live; "
        "die Fundamentaldaten darunter kommen aus dem täglichen GitHub-Workflow."
    )


# ------------------------------------------------------------
# Tab: Investmentthese
# ------------------------------------------------------------

with thesis:
    st.subheader("These prüfen statt Kurs erraten")

    st.markdown(
        """
**Deine Kernfrage:** Wird Solana in den nächsten Jahren wichtiger als Infrastruktur für digitale Finanzmärkte?

Positive Bestätigung kommt vor allem durch:

- steigende RWA-Werte und RWA-Holder,
- wachsende Stablecoin-Liquidität,
- stabiles oder steigendes TVL in SOL,
- reale Zahlungs- und Finanzpartner,
- technische Stabilität und Upgrades,
- relative Stärke gegenüber BTC.
        """
    )

    watchlist = load_watchlist()

    if watchlist:
        st.subheader("Manuelle Ereignis-Watchlist")
        st.dataframe(
            pd.DataFrame(watchlist),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.caption(
            "Optional: `watchlist.json` anlegen, um Ereignisse wie MoneyGram, "
            "bitFlyer, Agave/Alpenglow oder ETF-Meilensteine manuell zu verfolgen."
        )


# ------------------------------------------------------------
# Tab: News
# ------------------------------------------------------------

with news:
    st.subheader("Reddit & KI-News Monitor")

    st.caption(
        "Dieser Bereich sammelt Solana-relevante Nachrichten und Reddit-Beiträge "
        "und ordnet sie automatisch für deine Investmentthese ein. "
        "Die Bewertung ist regelbasiert, also keine echte Anlageberatung."
    )

    news_items = fetch_news(max_items_per_feed=4)

    if not news_items:
        st.info("Keine News gefunden.")
    else:
        for item in news_items:
            classification = item.get("classification", "🟡 Neutral")
            title = item.get("title", "Ohne Titel")
            source = item.get("source", "")
            published = item.get("published", "")
            link = item.get("link", "")

            if "🟢" in classification:
                st.success(f"{classification} – {title}")
            elif "🔴" in classification:
                st.error(f"{classification} – {title}")
            else:
                st.info(f"{classification} – {title}")

            st.caption(f"{source} · {published}")

            if link:
                st.markdown(f"[Quelle öffnen]({link})")

            st.divider()


# ------------------------------------------------------------
# Tab: Verlauf
# ------------------------------------------------------------

with history:
    st.subheader("Verlauf")

    options = {
        "fundamental_score": "Fundamental Score",
        "sol_usd": "SOL/USD",
        "sol_btc": "SOL/BTC",
        "tvl_usd": "TVL USD",
        "tvl_sol": "TVL in SOL",
        "stablecoins_usd": "Stablecoins",
        "rwa_usd": "RWA",
        "dex_volume_usd": "DEX Volumen",
        "fees_usd": "Fees",
    }

    choice = st.selectbox(
        "Kennzahl",
        list(options),
        format_func=lambda x: options[x]
    )

    chart_df = df.set_index("snapshot_date")[[choice]].dropna()
    st.line_chart(chart_df)


# ------------------------------------------------------------
# Tab: Rohdaten
# ------------------------------------------------------------

with raw:
    st.subheader("Rohdaten")

    st.dataframe(
        df.sort_values("snapshot_date", ascending=False),
        use_container_width=True
    )
