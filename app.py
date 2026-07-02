from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

try:
    import plotly.graph_objects as go
except Exception:
    go = None

from dotenv import load_dotenv

try:
    from supabase import create_client
except Exception:
    create_client = None

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


COINBASE_CANDLE_GRANULARITIES = {
    "1 Minute": 60,
    "5 Minuten": 300,
    "15 Minuten": 900,
    "1 Stunde": 3600,
    "6 Stunden": 21600,
    "1 Tag": 86400,
}

COINBASE_RANGE_DAYS = {
    "1 Tag": 1,
    "7 Tage": 7,
    "30 Tage": 30,
    "90 Tage": 90,
    "1 Jahr": 365,
}


def _coinbase_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@st.cache_data(ttl=60)
def fetch_coinbase_candles(product_id: str = "SOL-USD", days: int = 7, granularity: int = 3600) -> pd.DataFrame:
    """
    Lädt OHLC-Kerzen von Coinbase Exchange.
    Coinbase liefert pro Anfrage maximal ca. 300 Kerzen; deshalb wird in Blöcken abgefragt.
    Rückgabe-Spalten: time, low, high, open, close, volume
    """
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(days=days)
    max_points_per_request = 280
    step = pd.Timedelta(seconds=granularity * max_points_per_request)

    rows = []
    cursor = start
    headers = {"User-Agent": "solana-fundamental-monitor/2.0"}

    while cursor < end:
        chunk_end = min(cursor + step, end)
        url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
        params = {
            "granularity": granularity,
            "start": _coinbase_iso(cursor.to_pydatetime() if hasattr(cursor, "to_pydatetime") else cursor),
            "end": _coinbase_iso(chunk_end.to_pydatetime() if hasattr(chunk_end, "to_pydatetime") else chunk_end),
        }

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            pass

        cursor = chunk_end

    if not rows:
        return pd.DataFrame(columns=["time", "low", "high", "open", "close", "volume"])

    df_candles = pd.DataFrame(rows, columns=["timestamp", "low", "high", "open", "close", "volume"])
    df_candles = df_candles.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df_candles["time"] = pd.to_datetime(df_candles["timestamp"], unit="s", utc=True)

    for col in ["low", "high", "open", "close", "volume"]:
        df_candles[col] = pd.to_numeric(df_candles[col], errors="coerce")

    return df_candles[["time", "low", "high", "open", "close", "volume"]].dropna()


def render_candlestick_chart(candles: pd.DataFrame, title: str = "SOL/USD Candlestick Chart"):
    if candles.empty:
        st.warning("Keine Candle-Daten gefunden. Bitte später erneut versuchen oder einen anderen Zeitraum wählen.")
        return

    if go is None:
        st.warning("Plotly ist nicht installiert. Bitte `plotly>=5.24.0` in requirements.txt ergänzen. Fallback: Linienchart.")
        fallback = candles.set_index("time")[["close"]].rename(columns={"close": "SOL/USD"})
        st.line_chart(fallback, use_container_width=True)
        return

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=candles["time"],
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name="SOL/USD",
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title="Zeit",
        yaxis_title="Preis in USD",
        height=560,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def get_secret(name: str, fallback: str | None = None) -> str | None:
    """Liest erst Streamlit Secrets, dann Umgebungsvariablen."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, fallback)


def get_supabase_client():
    """Erstellt einen Supabase-Client für Login und private Portfolio-Daten."""
    url = get_secret("SUPABASE_URL")
    anon_key = (
        get_secret("SUPABASE_ANON_KEY")
        or get_secret("SUPABASE_KEY")
        or get_secret("SUPABASE_PUBLIC_KEY")
    )

    if create_client is None or not url or not anon_key:
        return None

    client = create_client(url, anon_key)

    access_token = st.session_state.get("sb_access_token")
    refresh_token = st.session_state.get("sb_refresh_token")

    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            pass

    return client


def store_supabase_session(response) -> bool:
    """Speichert Login-Informationen in der Streamlit-Session."""
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)

    if user is None:
        return False

    st.session_state["sb_user_id"] = getattr(user, "id", None)
    st.session_state["sb_user_email"] = getattr(user, "email", None)

    if session is not None:
        st.session_state["sb_access_token"] = getattr(session, "access_token", None)
        st.session_state["sb_refresh_token"] = getattr(session, "refresh_token", None)

    return True


def logout_supabase():
    for key in [
        "sb_user_id",
        "sb_user_email",
        "sb_access_token",
        "sb_refresh_token",
    ]:
        st.session_state.pop(key, None)


def load_user_position(client, user_id: str) -> dict:
    if client is None or not user_id:
        return {}

    try:
        result = (
            client.table("user_positions")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = getattr(result, "data", None) or []
        return data[0] if data else {}
    except Exception as exc:
        st.sidebar.warning(f"Position konnte nicht geladen werden: {exc}")
        return {}


def save_user_position(
    client,
    user_id: str,
    email: str | None,
    jitosol_amount: float,
    sol_equivalent: float,
    avg_entry_jitosol: float,
    historical_sol_entry: float,
) -> bool:
    if client is None or not user_id:
        return False

    payload = {
        "user_id": user_id,
        "email": email,
        "jitosol_amount": float(jitosol_amount),
        "sol_equivalent": float(sol_equivalent),
        "avg_entry_jitosol_usd": float(avg_entry_jitosol),
        "historical_sol_entry_usd": float(historical_sol_entry),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        client.table("user_positions").upsert(payload, on_conflict="user_id").execute()
        return True
    except Exception as exc:
        st.sidebar.error(f"Position konnte nicht gespeichert werden: {exc}")
        return False


def render_auth_area(client):
    """Login-/Signup-Bereich in der Sidebar."""
    user_id = st.session_state.get("sb_user_id")
    user_email = st.session_state.get("sb_user_email")

    if client is None:
        st.info(
            "Login ist noch nicht konfiguriert. Hinterlege SUPABASE_URL und "
            "SUPABASE_ANON_KEY in Streamlit Secrets."
        )
        return None, None, False

    if user_id:
        st.success(f"Eingeloggt als {user_email}")
        if st.button("Logout"):
            try:
                client.auth.sign_out()
            except Exception:
                pass
            logout_supabase()
            st.rerun()
        return user_id, user_email, True

    st.subheader("Login")

    auth_mode = st.radio(
        "Aktion",
        ["Einloggen", "Konto erstellen"],
        horizontal=True,
        label_visibility="collapsed",
    )

    email = st.text_input("E-Mail", key="auth_email")
    password = st.text_input("Passwort", type="password", key="auth_password")

    if st.button(auth_mode):
        if not email or not password:
            st.warning("Bitte E-Mail und Passwort eingeben.")
            return None, None, False

        try:
            if auth_mode == "Konto erstellen":
                response = client.auth.sign_up({"email": email, "password": password})
                if store_supabase_session(response):
                    st.success("Konto erstellt und eingeloggt.")
                    st.rerun()
                else:
                    st.info(
                        "Konto erstellt. Bitte prüfe ggf. deine E-Mail zur Bestätigung "
                        "und logge dich danach ein."
                    )
            else:
                response = client.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                if store_supabase_session(response):
                    st.success("Login erfolgreich.")
                    st.rerun()
                else:
                    st.error("Login fehlgeschlagen.")
        except Exception as exc:
            st.error(f"Login fehlgeschlagen: {exc}")

    return None, None, False


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
# Sidebar: Login + Deine Position
# ------------------------------------------------------------

with st.sidebar:
    st.header("Deine Position")

    supabase_client = get_supabase_client()
    user_id, user_email, is_logged_in = render_auth_area(supabase_client)

    st.divider()

    position = load_user_position(supabase_client, user_id) if is_logged_in else {}

    jitosol_amount = st.number_input(
        "JitoSOL Bestand",
        min_value=0.0,
        value=safe_float(position.get("jitosol_amount"), 0.0),
        step=0.01,
        format="%.5f"
    )

    sol_equivalent = st.number_input(
        "≈ SOL Gegenwert",
        min_value=0.0,
        value=safe_float(position.get("sol_equivalent"), 0.0),
        step=0.01,
        format="%.2f"
    )

    avg_entry_jitosol = st.number_input(
        "Ø Einstieg JitoSOL USD",
        min_value=0.0,
        value=safe_float(position.get("avg_entry_jitosol_usd"), 0.0),
        step=0.01,
        format="%.2f"
    )

    historical_sol_entry = st.number_input(
        "Historischer SOL-Einstieg USD",
        min_value=0.0,
        value=safe_float(position.get("historical_sol_entry_usd"), 0.0),
        step=1.0,
        format="%.2f"
    )

    if is_logged_in:
        if st.button("Position speichern"):
            ok = save_user_position(
                supabase_client,
                user_id,
                user_email,
                jitosol_amount,
                sol_equivalent,
                avg_entry_jitosol,
                historical_sol_entry,
            )
            if ok:
                st.success("Position gespeichert.")
                st.rerun()
    else:
        st.caption(
            "Ohne Login gelten die Werte nur für diese Sitzung. "
            "Mit Login werden sie privat in Supabase gespeichert."
        )

    st.divider()

    # JitoSOL/SOL-Umtauschkurs:
    # Bevorzugt live über CoinGecko-Preise; Fallback ist der von dir gespeicherte SOL-Gegenwert.
    entered_jitosol_sol_ratio = sol_equivalent / jitosol_amount if jitosol_amount else 0.0
    if jitosol_usd_live and sol_usd_live:
        jitosol_sol_ratio = float(jitosol_usd_live) / float(sol_usd_live)
    else:
        jitosol_sol_ratio = entered_jitosol_sol_ratio

    current_sol_equivalent = jitosol_amount * jitosol_sol_ratio

    if jitosol_usd_live:
        current_jitosol_price_usd = float(jitosol_usd_live)
    else:
        current_jitosol_price_usd = jitosol_sol_ratio * sol_usd_live

    if jitosol_eur_live:
        current_jitosol_price_eur = float(jitosol_eur_live)
    elif sol_eur_live:
        current_jitosol_price_eur = jitosol_sol_ratio * float(sol_eur_live)
    else:
        current_jitosol_price_eur = None

    value_now_usd = jitosol_amount * current_jitosol_price_usd
    value_now_eur = jitosol_amount * current_jitosol_price_eur if current_jitosol_price_eur else None

    cost_basis = jitosol_amount * avg_entry_jitosol
    pnl = value_now_usd - cost_basis
    pnl_pct = (value_now_usd / cost_basis - 1) * 100 if cost_basis else 0

    staking_sol_estimate = max(current_sol_equivalent - jitosol_amount, 0.0)
    staking_value_usd = staking_sol_estimate * sol_usd_live
    staking_value_eur = staking_sol_estimate * float(sol_eur_live) if sol_eur_live else None

    st.metric("Aktueller JitoSOL Preis", fmt_usd(current_jitosol_price_usd))
    if current_jitosol_price_eur:
        st.caption(f"≈ {current_jitosol_price_eur:.2f} EUR pro JitoSOL")
    st.caption(f"1 JitoSOL ≈ {jitosol_sol_ratio:.4f} SOL")

    st.metric("Aktueller Wert USD", fmt_usd(value_now_usd))
    st.metric("Aktueller Wert EUR", "n/a" if value_now_eur is None else f"{value_now_eur:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    st.caption(f"{jitosol_amount:.5f} JitoSOL ≈ {current_sol_equivalent:.2f} SOL")

    st.metric(
        "Buchgewinn/-verlust",
        fmt_usd(pnl),
        delta=f"{pnl_pct:+.1f}%"
    )

    st.metric("Geschätzter Staking-Zuwachs", f"{staking_sol_estimate:.4f} SOL")
    st.caption(
        "≈ " + fmt_usd(staking_value_usd)
        + (" / " + f"{staking_value_eur:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") if staking_value_eur is not None else "")
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

    st.divider()
    st.subheader("SOL/USD Candlestick Chart")

    chart_range = st.radio(
        "Zeitraum",
        ["1 Tag", "7 Tage", "30 Tage", "90 Tage", "1 Jahr"],
        index=1,
        horizontal=True,
    )

    chart_granularity_label = st.selectbox(
        "Kerzenintervall",
        ["1 Minute", "5 Minuten", "15 Minuten", "1 Stunde", "6 Stunden", "1 Tag"],
        index=3,
    )

    days = COINBASE_RANGE_DAYS.get(chart_range, 7)
    granularity = COINBASE_CANDLE_GRANULARITIES.get(chart_granularity_label, 3600)

    # Coinbase begrenzt die Anzahl Kerzen pro Request. Wir laden deshalb automatisch in Blöcken.
    candles = fetch_coinbase_candles("SOL-USD", days=days, granularity=granularity)
    render_candlestick_chart(candles, f"SOL/USD – {chart_range}, Kerzen: {chart_granularity_label}")

    if not candles.empty:
        last_close = safe_float(candles.iloc[-1].get("close"))
        first_close = safe_float(candles.iloc[0].get("close"))
        range_change = ((last_close / first_close) - 1) * 100 if first_close else None

        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Letzter Coinbase Close", fmt_usd(last_close))
        cc2.metric("Veränderung im Zeitraum", "n/a" if range_change is None else fmt_pct(range_change))
        cc3.metric("Kerzen", fmt_num(len(candles), 0))

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
