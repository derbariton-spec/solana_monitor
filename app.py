from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from auth import current_user, is_logged_in, load_user_position, render_auth_box, render_logged_in_box, save_user_position
from charts import render_candlestick_chart, render_line_history
from config import (
    APP_TITLE,
    APP_VERSION,
    CANDLE_INTERVALS,
    CANDLE_RANGES,
    DEFAULT_COINGLASS_EXCHANGE,
    DEFAULT_COINGLASS_PAIR,
    DEFAULT_COINGLASS_SYMBOL,
    DEFAULT_PRODUCT_ID,
    SOLANA_LOGO_URL,
)
from data_sources import (
    fetch_coinglass_heatmap,
    fetch_coinbase_candles,
    fetch_live_market,
    fetch_snapshot,
    summarize_liquidation_levels,
)
from formatting import fmt_datetime_utc, fmt_eur, fmt_number, fmt_pct, fmt_usd, is_missing, safe_float
from market_intelligence import build_market_intelligence
from market_signals import build_market_signal_report, signal_rows
from news_fetcher import fetch_news
from portfolio import PositionSettings, compute_portfolio
from user_profile import (
    ScenarioPreferences,
    UserProfile,
    WatchLevels,
    load_recent_notes,
    load_scenario_preferences,
    load_user_profile,
    load_watch_levels,
    save_daily_note,
    save_scenario_preferences,
    save_user_profile,
    save_watch_levels,
)
from quality import build_data_quality_rows, quality_summary
from reports import weekly_report_rows
from risk import build_risk_rows
from scenario import DEFAULT_TARGETS, build_price_scenarios
from scoring import compute_fundamental_score, interpretation_text, traffic_light
from storage import load_history
from thesis import compute_subscores, score_explanation, thesis_break_rules
from wallet import fetch_wallet_summary

APP_ICON_PATH = Path(__file__).parent / "assets" / "app-icon.png"
try:
    PAGE_ICON = Image.open(APP_ICON_PATH) if APP_ICON_PATH.exists() else "🟣"
except Exception:
    PAGE_ICON = "🟣"

st.set_page_config(page_title=APP_TITLE, page_icon=PAGE_ICON, layout="wide")



def inject_ios_pwa_icons() -> None:
    """Inject Apple touch icon + PWA manifest links into the document head.

    Streamlit's page_icon is not always picked up by iOS when adding the app
    to the Home Screen. Static serving + explicit apple-touch-icon links are
    more reliable on Safari/iOS.
    """
    components.html(
        """
<script>
(function() {
  const doc = window.parent.document;
  const head = doc.head;

  function upsertLink(selector, attrs) {
    let el = head.querySelector(selector);
    if (!el) {
      el = doc.createElement('link');
      head.appendChild(el);
    }
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  }

  function upsertMeta(selector, attrs) {
    let el = head.querySelector(selector);
    if (!el) {
      el = doc.createElement('meta');
      head.appendChild(el);
    }
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  }

  const base = window.parent.location.origin;
  const icon180 = base + '/app/static/apple-touch-icon.png?v=5.3.6';
  const icon192 = base + '/app/static/app-icon-192.png?v=5.3.6';
  const icon512 = base + '/app/static/app-icon-512.png?v=5.3.6';
  const manifest = base + '/app/static/manifest.json?v=5.3.6';

  upsertLink('link[rel="apple-touch-icon"]', {rel: 'apple-touch-icon', sizes: '180x180', href: icon180});
  upsertLink('link[rel="icon"][sizes="192x192"]', {rel: 'icon', type: 'image/png', sizes: '192x192', href: icon192});
  upsertLink('link[rel="icon"][sizes="512x512"]', {rel: 'icon', type: 'image/png', sizes: '512x512', href: icon512});
  upsertLink('link[rel="manifest"]', {rel: 'manifest', href: manifest});

  upsertMeta('meta[name="apple-mobile-web-app-capable"]', {name: 'apple-mobile-web-app-capable', content: 'yes'});
  upsertMeta('meta[name="apple-mobile-web-app-title"]', {name: 'apple-mobile-web-app-title', content: 'Solana Terminal'});
  upsertMeta('meta[name="theme-color"]', {name: 'theme-color', content: '#080812'});
})();
</script>
        """,
        height=0,
        width=0,
    )


# -----------------------------
# Visual design helpers (v5.3)
# -----------------------------

def inject_theme_css() -> None:
    st.markdown(
        """
<style>
:root {
  --sol-bg-1: #080812;
  --sol-bg-2: #11111f;
  --sol-card: rgba(255,255,255,0.055);
  --sol-card-strong: rgba(255,255,255,0.082);
  --sol-border: rgba(255,255,255,0.12);
  --sol-text-muted: rgba(255,255,255,0.68);
  --sol-green: #14F195;
  --sol-purple: #9945FF;
  --sol-blue: #00D4FF;
  --sol-yellow: #FFD166;
  --sol-red: #FF5C7A;
}
.stApp {
  background:
    radial-gradient(circle at 10% 0%, rgba(153,69,255,0.18), transparent 32%),
    radial-gradient(circle at 90% 10%, rgba(20,241,149,0.12), transparent 30%),
    linear-gradient(180deg, var(--sol-bg-1), var(--sol-bg-2));
}
.block-container { padding-top: 1.25rem; max-width: 1500px; }
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(16,16,30,0.96), rgba(8,8,18,0.98));
  border-right: 1px solid var(--sol-border);
}
.sol-hero {
  border: 1px solid var(--sol-border);
  background: linear-gradient(135deg, rgba(153,69,255,0.18), rgba(20,241,149,0.07)), rgba(255,255,255,0.045);
  border-radius: 28px;
  padding: 26px 28px;
  margin: 0.2rem 0 1.0rem 0;
  box-shadow: 0 24px 80px rgba(0,0,0,0.35);
}
.sol-hero-row { display: flex; gap: 16px; align-items: center; }
.sol-logo { width: 58px; height: 58px; border-radius: 18px; background: rgba(255,255,255,0.06); padding: 8px; }
.sol-title { font-size: clamp(2.0rem, 4vw, 3.8rem); font-weight: 900; line-height: 1.0; letter-spacing: -0.06em; margin: 0; }
.sol-subtitle { color: var(--sol-text-muted); font-size: 1.02rem; margin-top: 8px; }
.sol-pill {
  display: inline-block; padding: 5px 10px; border-radius: 999px; font-weight: 800; font-size: 0.78rem;
  background: rgba(20,241,149,0.12); color: var(--sol-green); border: 1px solid rgba(20,241,149,0.25); margin-left: 8px;
}
.sol-card-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; margin: 12px 0 18px 0; }
.sol-card {
  border: 1px solid var(--sol-border); background: var(--sol-card); border-radius: 22px; padding: 18px 18px;
  min-height: 112px; box-shadow: 0 12px 42px rgba(0,0,0,0.20); backdrop-filter: blur(12px);
}
.sol-card:hover { background: var(--sol-card-strong); border-color: rgba(255,255,255,0.18); }
.sol-card-label { color: var(--sol-text-muted); font-size: 0.86rem; font-weight: 800; letter-spacing: .02em; text-transform: uppercase; }
.sol-card-value { color: white; font-size: clamp(1.55rem, 2.6vw, 2.35rem); font-weight: 900; margin-top: 8px; letter-spacing: -0.04em; }
.sol-card-caption { color: var(--sol-text-muted); font-size: .88rem; margin-top: 6px; }
.sol-card.good { border-color: rgba(20,241,149,0.32); box-shadow: inset 0 0 0 1px rgba(20,241,149,0.06); }
.sol-card.warn { border-color: rgba(255,209,102,0.32); }
.sol-card.bad { border-color: rgba(255,92,122,0.34); }
.sol-card.info { border-color: rgba(0,212,255,0.28); }
.sol-section-title { font-size: 1.55rem; font-weight: 900; margin: 1.1rem 0 .55rem 0; letter-spacing: -0.03em; }
.sol-summary-box {
  border: 1px solid rgba(153,69,255,0.28); background: linear-gradient(135deg, rgba(153,69,255,0.15), rgba(0,212,255,0.05));
  border-radius: 22px; padding: 18px 20px; margin: 10px 0 16px 0; color: rgba(255,255,255,0.92);
}
.sol-badge-good, .sol-badge-warn, .sol-badge-bad, .sol-badge-info {
  display:inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 850; font-size: .78rem;
}
.sol-badge-good { background: rgba(20,241,149,0.14); color: var(--sol-green); border: 1px solid rgba(20,241,149,0.25); }
.sol-badge-warn { background: rgba(255,209,102,0.14); color: var(--sol-yellow); border: 1px solid rgba(255,209,102,0.25); }
.sol-badge-bad { background: rgba(255,92,122,0.14); color: var(--sol-red); border: 1px solid rgba(255,92,122,0.25); }
.sol-badge-info { background: rgba(0,212,255,0.14); color: var(--sol-blue); border: 1px solid rgba(0,212,255,0.25); }
div[data-testid="stMetric"] {
  background: rgba(255,255,255,0.055); border: 1px solid var(--sol-border); border-radius: 20px; padding: 14px 16px;
}
div[data-testid="stDataFrame"] { border-radius: 18px; overflow: hidden; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] {
  border: 1px solid rgba(255,255,255,0.10); border-radius: 999px; padding: 8px 14px; background: rgba(255,255,255,0.04);
}
.stTabs [aria-selected="true"] { background: linear-gradient(90deg, rgba(153,69,255,0.25), rgba(20,241,149,0.14)); }
@media (max-width: 900px) {
  .sol-card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .sol-hero { padding: 20px 18px; border-radius: 22px; }
  .sol-logo { width: 46px; height: 46px; border-radius: 14px; }
}
@media (max-width: 520px) {
  .sol-card-grid { grid-template-columns: 1fr; }
  .sol-title { font-size: 2.1rem; }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _tone_for_score(score: float | None) -> str:
    if score is None:
        return "info"
    if score >= 70:
        return "good"
    if score >= 50:
        return "warn"
    return "bad"


def _status_tone(status: str | None) -> str:
    if status == "intakt":
        return "good"
    if status == "geschwaecht":
        return "bad"
    return "warn"


def _card(label: str, value: str, caption: str = "", tone: str = "info") -> str:
    return f"""
    <div class="sol-card {tone}">
      <div class="sol-card-label">{label}</div>
      <div class="sol-card-value">{value}</div>
      <div class="sol-card-caption">{caption}</div>
    </div>
    """


def _badge(text: str, tone: str = "info") -> str:
    return f'<span class="sol-badge-{tone}">{text}</span>'


def render_native_card(label: str, value: str, caption: str = "", tone: str = "info") -> None:
    """Render a card with native Streamlit elements so HTML is never printed as text."""
    with st.container(border=True):
        st.caption(str(label).upper())
        st.markdown(f"### {value}")
        if caption:
            st.caption(str(caption))


# -----------------------------
# Cached data access
# -----------------------------

@st.cache_data(ttl=30, show_spinner=False)
def cached_live_market() -> dict:
    return fetch_live_market()


@st.cache_data(ttl=300, show_spinner=False)
def cached_current_fundamentals() -> dict:
    return fetch_snapshot()


@st.cache_data(ttl=60, show_spinner=False)
def cached_candles(days: int, granularity: int) -> pd.DataFrame:
    return fetch_coinbase_candles(DEFAULT_PRODUCT_ID, days=days, granularity=granularity)


@st.cache_data(ttl=90, show_spinner=False)
def cached_wallet(wallet_address: str) -> dict:
    return fetch_wallet_summary(wallet_address)


@st.cache_data(ttl=300, show_spinner=False)
def cached_news() -> list[dict]:
    # Compatibility guard: if an older news_fetcher.py is still deployed/cached,
    # it may not accept the newer keyword arguments yet. The app should not crash
    # just because the news module is one commit behind.
    try:
        return fetch_news(max_items_per_feed=8, max_total=50)
    except TypeError:
        try:
            return fetch_news()
        except Exception as exc:
            return [{
                "source": "System",
                "title": f"News konnten nicht geladen werden: {exc}",
                "link": "",
                "published": "",
                "published_ts": 0.0,
                "summary": "",
                "category": "System",
                "classification": "🟡 Neutral",
            }]
    except Exception as exc:
        return [{
            "source": "System",
            "title": f"News konnten nicht geladen werden: {exc}",
            "link": "",
            "published": "",
            "published_ts": 0.0,
            "summary": "",
            "category": "System",
            "classification": "🟡 Neutral",
        }]


@st.cache_data(ttl=120, show_spinner=False)
def cached_coinglass(symbol: str, pair: str, exchange: str, model: str) -> dict:
    return fetch_coinglass_heatmap(symbol=symbol, pair=pair, exchange=exchange, model=model)


@st.cache_data(ttl=180, show_spinner=False)
def cached_market_signals(latest_key: str | None = None, past_key: str | None = None) -> dict:
    # Daily candles keep RSI/MACD stable enough for investment decisions.
    candles = fetch_coinbase_candles(DEFAULT_PRODUCT_ID, days=180, granularity=86400)
    # latest_key/past_key only invalidate cache when fundamentals history changes; real dicts are set in caller below.
    return {"candles": candles}


# -----------------------------
# Data helpers
# -----------------------------

def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    out = {}
    for k, v in row.to_dict().items():
        if is_missing(v):
            out[k] = None
        elif isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def pct_delta(latest: dict | pd.Series | None, prev: dict | pd.Series | None, key: str) -> float | None:
    if latest is None or prev is None:
        return None
    try:
        cur = latest.get(key)
        old = prev.get(key)
        if pd.isna(cur) or pd.isna(old) or float(old) == 0:
            return None
        return (float(cur) - float(old)) / float(old) * 100
    except Exception:
        return None


def merge_missing_current_metrics(latest: dict | None) -> dict | None:
    """Use live current API data as fallback when the CSV row still has blanks."""
    if latest is None:
        return None
    enriched = dict(latest)
    try:
        current = cached_current_fundamentals()
    except Exception:
        return enriched
    fallback_keys = [
        "rwa_usd",
        "active_addresses",
        "transactions_24h",
        "chain_fees_usd",
        "chain_revenue_usd",
        "app_fees_usd",
        "app_revenue_usd",
        "dex_volume_usd",
        "stablecoins_usd",
        "tvl_usd",
        "tvl_sol",
        "sol_usd",
        "sol_btc",
        "btc_usd",
        "btc_dominance",
    ]
    for key in fallback_keys:
        if is_missing(enriched.get(key)) and not is_missing(current.get(key)):
            enriched[key] = current.get(key)
    return enriched


def get_latest_context():
    df = load_history(days=3650)
    if df.empty:
        return df, None, None, None, compute_fundamental_score({}, None, None)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")
    df = df.dropna(subset=["snapshot_date"]).sort_values("snapshot_date")
    latest_row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    target = latest_row["snapshot_date"] - pd.Timedelta(days=30)
    past_candidates = df[df["snapshot_date"] <= target]
    past = past_candidates.iloc[-1] if not past_candidates.empty else None
    latest = merge_missing_current_metrics(row_to_dict(latest_row))
    result = compute_fundamental_score(latest or {}, row_to_dict(past) if past is not None else None, df)
    return df, latest, prev, past, result


def get_portfolio_snapshot(live: dict, mode: str = "public"):
    if mode != "personal" or not is_logged_in():
        position = PositionSettings()
        wallet_summary = {"ok": False, "error": "Public Mode: keine persönliche Wallet geladen."}
        portfolio = compute_portfolio(position, wallet_summary, live)
        return position, wallet_summary, portfolio
    position = load_user_position()
    wallet_summary = cached_wallet(position.wallet_address) if position.wallet_address else {"ok": False, "error": "Keine Wallet hinterlegt."}
    portfolio = compute_portfolio(position, wallet_summary, live)
    return position, wallet_summary, portfolio


# -----------------------------
# Header and top metrics
# -----------------------------

def render_header() -> None:
    st.markdown(
        f"""
<div class="sol-hero">
  <div class="sol-hero-row">
    <img class="sol-logo" src="{SOLANA_LOGO_URL}" />
    <div>
      <div class="sol-title">Solana Intelligence Terminal <span class="sol-pill">v{APP_VERSION}</span></div>
      <div class="sol-subtitle">Thesis Score · Market Signals · Wallet/JitoSOL · Risk · Szenarien · Multi-User Public/Personal Mode</div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_refresh_controls() -> None:
    """Manual refresh button for iPhone/home-screen usage.

    Streamlit caches live market, wallet, news and fundamentals data.
    On iOS home-screen mode the browser refresh gesture is not always obvious,
    so this button clears the cache and reruns the app immediately.
    """
    left, right = st.columns([0.72, 0.28])
    with left:
        last_refresh = st.session_state.get("last_manual_refresh")
        if last_refresh:
            st.caption(f"Letzte manuelle Aktualisierung: {last_refresh}")
        else:
            st.caption("Live-Daten werden gecacht. Über den Button kannst du alles sofort neu laden.")
    with right:
        if st.button("🔄 Werte aktualisieren", use_container_width=True, key="manual_refresh_button"):
            st.cache_data.clear()
            st.session_state["last_manual_refresh"] = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            st.rerun()


def render_mode_selector() -> str:
    """Switch between public research view and private portfolio workspace."""
    st.sidebar.markdown("## Modus")
    default_idx = 1 if is_logged_in() else 0
    mode = st.sidebar.radio(
        "Ansicht",
        ["🌍 Public Mode", "🔐 Personal Mode"],
        index=default_idx,
        help="Public Mode zeigt allgemeine Solana-Daten. Personal Mode ergänzt Login, Wallet, Watch-Level, Szenarien und Notizen.",
    )
    if mode.startswith("🔐") and not is_logged_in():
        st.sidebar.info("Personal Mode benötigt Login. Du kannst dich direkt hier anmelden oder im Tab Profil & Onboarding.")
        with st.sidebar.container():
            st.markdown("### 🔐 Login")
            render_auth_box(key_prefix="sidebar_personal_login")
    elif is_logged_in():
        st.sidebar.divider()
        render_logged_in_box(key_prefix="sidebar_login_status", compact=True)
    return "personal" if mode.startswith("🔐") else "public"


def render_onboarding_notice() -> None:
    if not is_logged_in():
        return
    profile = load_user_profile()
    if not profile.onboarding_completed:
        st.warning("Profil-Onboarding noch nicht abgeschlossen. Öffne den Tab Profil & Onboarding, um Wallet, Watch-Level und Szenarien sauber einzurichten.")


def render_top_metrics(latest, live: dict, result: dict, portfolio: dict | None = None, mode: str = "public") -> None:
    score = safe_float(result.get("score"), 50)
    status = result.get("status", "neutral")
    status_label = "These intakt" if status == "intakt" else "These geschwächt" if status == "geschwaecht" else "neutral"
    sol_usd = safe_float(live.get("sol_usd"), safe_float(latest.get("sol_usd") if latest is not None else None))
    sol_eur = live.get("sol_eur")
    sol_24h = live.get("sol_24h_change")
    sol_btc = safe_float(live.get("sol_btc"), safe_float(latest.get("sol_btc") if latest is not None else None))
    portfolio_eur = None if not portfolio else portfolio.get("total_eur")

    card_data = [
        ("Thesis", status_label, interpretation_text(result), _status_tone(status)),
        ("Score", f"{score:.0f}/100", "Fundamental + Struktur", _tone_for_score(score)),
        ("SOL/USD", f"{sol_usd:.2f} $", (fmt_pct(sol_24h) + " 24h") if sol_24h is not None else "Live", "info"),
        ("SOL/EUR", "n/a" if sol_eur is None else f"{float(sol_eur):.2f} €", "für Portfolio-Sicht", "info"),
        ("Portfolio" if mode == "personal" else "SOL/BTC", fmt_eur(portfolio_eur) if mode == "personal" and portfolio_eur is not None else f"{sol_btc:.6f}", "Personal Mode" if mode == "personal" else "Relative Stärke", "good" if mode == "personal" else "info"),
    ]

    cols = st.columns(len(card_data))
    for col, (label, value, caption, tone) in zip(cols, card_data):
        with col:
            render_native_card(label, value, caption, tone)

    st.progress(max(0, min(int(score), 100)) / 100)
    st.caption(f"Live-Kurs zuletzt abgefragt: {fmt_datetime_utc(live.get('timestamp'))}")


# -----------------------------
# Individual tabs
# -----------------------------

def render_overview_tab(df, latest, result, live, wallet_summary) -> None:
    score = safe_float(result.get("score"), 50)
    status = result.get("status", "neutral")
    status_text = "intakt" if status == "intakt" else "geschwächt" if status == "geschwaecht" else "neutral"
    st.markdown("<div class='sol-section-title'>Heute wichtig</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="sol-summary-box">
  <b>Solana-These: {status_text}</b> · Score <b>{score:.0f}/100</b><br/>
  {interpretation_text(result)}
</div>
""",
        unsafe_allow_html=True,
    )

    sub_rows = compute_subscores(result)
    if sub_rows:
        cols = st.columns(min(3, max(1, len(sub_rows[:6]))))
        for i, row in enumerate(sub_rows[:6]):
            val = safe_float(row.get("Score"), 50)
            with cols[i % len(cols)]:
                render_native_card(str(row.get("Bereich", "Score")), f"{val:.0f}/100", str(row.get("Kommentar", "")), _tone_for_score(val))

    explanation = score_explanation(result)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### Positive Treiber")
        if explanation["positive"]:
            for line in explanation["positive"]:
                st.success(line)
        else:
            st.info("Noch keine klaren positiven Treiber.")
    with col2:
        st.markdown("### Belastungsfaktoren")
        if explanation["negative"]:
            for line in explanation["negative"]:
                st.warning(line)
        else:
            st.success("Keine starken negativen Treiber im Score.")
    with col3:
        st.markdown("### Datenabdeckung")
        quality_rows = build_data_quality_rows(latest, df, live, wallet_summary)
        st.write(quality_summary(quality_rows))
        if latest is not None:
            st.caption(f"Letzter Fundamentaldaten-Snapshot: {latest.get('snapshot_date')}")

    st.markdown("### These gebrochen?")
    st.dataframe(pd.DataFrame(thesis_break_rules(latest, df, result)), hide_index=True, use_container_width=True)

    with st.expander("Subscores als Tabelle anzeigen"):
        st.dataframe(pd.DataFrame(sub_rows), hide_index=True, use_container_width=True)


@st.cache_data(ttl=120, show_spinner=False)
def cached_intelligence_signal_report(latest_key: str | None = None, past_key: str | None = None) -> dict:
    candles = fetch_coinbase_candles(DEFAULT_PRODUCT_ID, days=90, granularity=21600)
    report = build_market_signal_report(candles, latest=None, past=None)
    return {"candles": candles, "report": report}


def _level_rows(levels: list[float], kind: str) -> list[dict[str, str]]:
    icon = "🔴" if kind == "Resistance" else "🟢"
    label = "Short-Liquidität / Breakout-Zone" if kind == "Resistance" else "Retest / Support-Zone"
    return [{"Typ": kind, "Level": f"{icon} {fmt_usd(level)}", "Lesart": label} for level in levels]


def render_market_intelligence_tab(latest: dict | None, past: dict | None, live: dict, portfolio: dict) -> None:
    st.subheader("🧠 SOL Market Intelligence")
    st.caption("Marktstruktur, technische Liquiditätszonen, Macro-Fallbacks und deine Portfolio-Exposure in einer Ansicht.")

    latest_key = str((latest or {}).get("snapshot_date"))
    past_key = str((past or {}).get("snapshot_date")) if past is not None else None
    cached = cached_intelligence_signal_report(latest_key, past_key)
    candles = cached.get("candles")
    signal_report = cached.get("report") or {}
    intelligence = build_market_intelligence(candles, live, portfolio, latest=latest, signal_report=signal_report)

    structure = intelligence["structure"]
    liquidity = intelligence["liquidity"]
    tech = structure.get("technical") or {}
    exposure_sol = safe_float(portfolio.get("sol_equivalent"), 0.0) + safe_float(portfolio.get("sol_balance"), 0.0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SOL/USD", fmt_usd(live.get("sol_usd")), None if live.get("sol_24h_change") is None else fmt_pct(live.get("sol_24h_change")) + " 24h")
    c2.metric("Trend", str(structure.get("label", "n/a")), (tech.get("macd_cross") or {}).get("label"))
    c3.metric("Liquidity Bias", str(liquidity.get("bias", "n/a")), f"↑ {liquidity.get('up_probability')}% / ↓ {liquidity.get('down_probability')}%")
    c4.metric("SOL Exposure", fmt_number(exposure_sol, 2), "Portfolio-Hebel pro SOL-$")

    st.markdown("### Key Levels")
    level_rows = []
    level_rows.extend(_level_rows(intelligence["levels"].get("resistance") or [], "Resistance"))
    level_rows.extend(_level_rows(intelligence["levels"].get("support") or [], "Support"))
    if level_rows:
        st.dataframe(pd.DataFrame(level_rows), hide_index=True, use_container_width=True)
    else:
        st.info("Noch keine belastbaren Swing-Level aus den aktuellen Kerzen ermittelt.")

    left, right = st.columns(2)
    with left:
        st.markdown("### Liquidity Engine")
        st.dataframe(
            pd.DataFrame([
                {"Signal": "Upside Liquidity", "Wert": ", ".join(fmt_usd(x) for x in liquidity.get("upside_targets") or []) or "n/a"},
                {"Signal": "Downside Liquidity", "Wert": ", ".join(fmt_usd(x) for x in liquidity.get("downside_targets") or []) or "n/a"},
                {"Signal": "Sweep higher", "Wert": f"{liquidity.get('up_probability')}%"},
                {"Signal": "Breakdown", "Wert": f"{liquidity.get('down_probability')}%"},
            ]),
            hide_index=True,
            use_container_width=True,
        )
    with right:
        st.markdown("### Your Position")
        st.metric("JitoSOL", fmt_number(portfolio.get("jitosol_amount"), 5), f"{fmt_number(portfolio.get('sol_equivalent'), 2)} SOL exposure")
        st.dataframe(pd.DataFrame(intelligence["position_rows"]), hide_index=True, use_container_width=True)

    st.markdown("### Macro Layer")
    st.dataframe(pd.DataFrame(intelligence["macro"]), hide_index=True, use_container_width=True)

    st.markdown("### AI Interpretation")
    st.info(intelligence["interpretation"])


def render_market_tab(live: dict) -> None:
    st.subheader("SOL/USD Candlestick")
    r_col, i_col = st.columns(2)
    with r_col:
        range_label = st.selectbox("Zeitraum", list(CANDLE_RANGES.keys()), index=1)
    with i_col:
        interval_label = st.selectbox("Kerzenintervall", list(CANDLE_INTERVALS.keys()), index=3)
    days = CANDLE_RANGES[range_label]
    granularity = CANDLE_INTERVALS[interval_label]
    candles = cached_candles(days, granularity)
    render_candlestick_chart(candles, f"SOL/USD · Coinbase · {range_label} · {interval_label}")
    st.caption("Coinbase begrenzt Kerzenabfragen. Bei kleinen Intervallen kann der dargestellte Zeitraum automatisch gekürzt werden.")

    st.divider()
    st.subheader("Live-Markt")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("SOL/USD", fmt_usd(live.get("sol_usd")), None if live.get("sol_24h_change") is None else fmt_pct(live.get("sol_24h_change")) + " 24h")
    m2.metric("SOL/EUR", fmt_eur(live.get("sol_eur")))
    m3.metric("JitoSOL/USD", fmt_usd(live.get("jitosol_usd")), None if live.get("jitosol_24h_change") is None else fmt_pct(live.get("jitosol_24h_change")) + " 24h")
    ratio = safe_float(live.get("jitosol_usd"), 0) / safe_float(live.get("sol_usd"), 1) if live.get("jitosol_usd") and live.get("sol_usd") else None
    m4.metric("JitoSOL/SOL", "n/a" if ratio is None else fmt_number(ratio, 6))


def render_market_signals_tab(latest: dict | None, past: dict | None) -> None:
    st.subheader("📡 Market Signals")
    st.caption("Timing-/Risiko-Modul: RSI, MACD, Engulfing, Funding Rate, Open Interest, Fear & Greed und Altcoin Season.")

    candles = fetch_coinbase_candles(DEFAULT_PRODUCT_ID, days=180, granularity=86400)
    report = build_market_signal_report(candles, latest=latest, past=row_to_dict(past) if hasattr(past, "to_dict") else past)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Timing Score", f"{report.get('timing_score', 0):.0f}/100", report.get("label"))
    c2.metric("Technicals", f"{report.get('technical_score', 0):.0f}/100")
    c3.metric("Derivatives", f"{report.get('derivatives_score', 0):.0f}/100")
    c4.metric("Sentiment", f"{report.get('sentiment_score', 0):.0f}/100")

    rows = signal_rows(report)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Positive Signale")
        positives = report.get("reasons_positive") or ["Keine klaren positiven Timing-Signale."]
        for line in positives:
            st.success(line)
    with col2:
        st.markdown("### Risiken")
        risks = report.get("reasons_risk") or ["Keine starken Timing-Risiken erkannt."]
        for line in risks:
            st.warning(line)

    st.markdown("### Lesart")
    st.write(
        "Der Timing Score ist kein Kauf-/Verkaufssignal. Er zeigt, ob Marktstruktur, Hebel und Sentiment gerade Rückenwind oder Risiko erzeugen. "
        "Für langfristige Entscheidungen sollte er neben dem Fundamental Score gelesen werden."
    )


def render_onboarding_tab(live: dict) -> None:
    st.subheader("🔐 Profil & Onboarding")
    st.caption("Hier wird aus dem privaten Monitor eine Multi-User-Version: Public Mode für alle, Personal Mode je Login getrennt per Supabase/RLS.")
    render_auth_box()
    st.divider()

    if not is_logged_in():
        st.info("Im Public Mode sind alle allgemeinen Solana-Daten sichtbar. Für Wallet, Watch-Level, Szenarien und Notizen bitte anmelden oder Account erstellen.")
        st.markdown("""
**Public Mode enthält:** Fundamentals, Score, Market Signals, News, Liquidationsbereich und Historie.

**Personal Mode ergänzt:** eigene Wallet, JitoSOL-Rewards, Einstandsdaten, Watch-Level, Szenario-Ziele und tägliche Notizen.
""")
        return

    user = current_user() or {}
    profile = load_user_profile()
    levels = load_watch_levels()
    prefs = load_scenario_preferences()

    st.success(f"Angemeldet als {user.get('email', 'Nutzer')}")

    with st.form("profile_onboarding_form"):
        st.markdown("### 1. Profil")
        display_name = st.text_input("Anzeigename", value=profile.display_name)
        investor_mode = st.selectbox("Nutzungsmodus", ["Public + Personal", "Nur Personal", "Nur Research"], index=["Public + Personal", "Nur Personal", "Nur Research"].index(profile.investor_mode) if profile.investor_mode in ["Public + Personal", "Nur Personal", "Nur Research"] else 0)
        risk_profile = st.selectbox("Risikoprofil", ["Konservativ", "Ausgewogen", "Offensiv"], index=["Konservativ", "Ausgewogen", "Offensiv"].index(profile.risk_profile) if profile.risk_profile in ["Konservativ", "Ausgewogen", "Offensiv"] else 1)

        st.markdown("### 2. Watch-Level")
        c1, c2 = st.columns(2)
        with c1:
            accumulation = st.number_input("Akkumulation unter USD", value=float(levels.accumulation_below_usd), min_value=1.0, step=5.0)
            warning_below = st.number_input("Warnung unter USD", value=float(levels.warning_below_usd), min_value=1.0, step=5.0)
            target = st.number_input("Langfristziel USD", value=float(levels.long_term_target_usd), min_value=1.0, step=25.0)
        with c2:
            hedge = st.number_input("Hedge prüfen über USD", value=float(levels.hedge_check_above_usd), min_value=1.0, step=5.0)
            profit = st.number_input("Teilgewinn prüfen über USD", value=float(levels.profit_check_above_usd), min_value=1.0, step=25.0)

        st.markdown("### 3. Szenarien")
        targets = st.text_input("SOL-Zielpreise USD, kommagetrennt", value=prefs.target_prices_csv)
        apy = st.number_input("JitoSOL APY-Annahme", value=float(prefs.jitosol_apy_assumption), min_value=0.0, max_value=25.0, step=0.1)

        completed = st.checkbox("Onboarding abgeschlossen", value=profile.onboarding_completed)
        submitted = st.form_submit_button("Profil speichern")

    if submitted:
        ok1 = save_user_profile(UserProfile(display_name=display_name.strip(), investor_mode=investor_mode, risk_profile=risk_profile, onboarding_completed=completed))
        ok2 = save_watch_levels(WatchLevels(accumulation_below_usd=accumulation, warning_below_usd=warning_below, hedge_check_above_usd=hedge, profit_check_above_usd=profit, long_term_target_usd=target))
        ok3 = save_scenario_preferences(ScenarioPreferences(target_prices_csv=targets, jitosol_apy_assumption=apy))
        if ok1 and ok2 and ok3:
            st.success("Profil, Watch-Level und Szenarien gespeichert.")

    st.divider()
    st.markdown("### Tägliche Notiz")
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    note = st.text_area("Markt-/Portfolio-Notiz", placeholder="z. B. Nachkauf geprüft, Hedge geschlossen, SOL/BTC stark, Makro unsicher …")
    if st.button("Notiz speichern"):
        if save_daily_note(today, note.strip()):
            st.success("Notiz gespeichert.")

    notes = load_recent_notes(10)
    if notes:
        st.markdown("### Letzte Notizen")
        st.dataframe(pd.DataFrame(notes), hide_index=True, use_container_width=True)


def render_staking_rewards_module(portfolio: dict) -> None:
    rewards_sol = portfolio.get("staking_rewards_sol")
    rewards_eur = portfolio.get("staking_rewards_eur")
    rewards_usd = portfolio.get("staking_rewards_usd")
    reward_prefix = "+" if safe_float(rewards_sol, 0.0) >= 0 else ""

    st.subheader("JitoSOL Staking Rewards")
    with st.container(border=True):
        if rewards_sol is None:
            st.warning(
                "Noch keine Rewards-Basis vorhanden. Trage entweder den Phantom-Wert "
                "'Bought' in SOL oder ein JitoSOL-Kauf-/Startdatum ein."
            )
            st.caption(
                "Formel: aktueller SOL-Gegenwert deiner JitoSOL minus netto eingebrachte SOL. "
                "Bei Liquid Staking wächst nicht die Token-Anzahl, sondern der JitoSOL/SOL-Kurs."
            )
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Rewards seit Start",
            f"{reward_prefix}{fmt_number(rewards_sol, 5)} SOL",
            fmt_eur(rewards_eur),
        )
        c2.metric("Reward-Wert USD", fmt_usd(rewards_usd))
        c3.metric(
            "Rendite in SOL",
            fmt_pct(portfolio.get("staking_rewards_pct")),
            None if portfolio.get("staking_apy") is None else f"APY {fmt_pct(portfolio.get('staking_apy'))}",
        )
        c4.metric(
            "Ø pro Tag",
            "n/a" if portfolio.get("staking_rewards_per_day_sol") is None else f"{fmt_number(portfolio.get('staking_rewards_per_day_sol'), 5)} SOL",
            None if portfolio.get("staking_rewards_per_day_eur") is None else fmt_eur(portfolio.get("staking_rewards_per_day_eur")),
        )

        st.caption(
            "Phantom-Logik: Holding in SOL minus Bought in SOL. "
            "Die App nutzt dafür den aktuellen JitoSOL/SOL-Kurs und deine gespeicherte Startbasis."
        )

        breakdown = [
            {"Position": "JitoSOL Menge", "Wert": fmt_number(portfolio.get("jitosol_amount"), 5), "Einheit": "JitoSOL"},
            {"Position": "Bought / Startbasis", "Wert": fmt_number(portfolio.get("staking_basis_sol"), 5), "Einheit": "SOL"},
            {"Position": "Holding heute", "Wert": fmt_number(portfolio.get("sol_equivalent"), 5), "Einheit": "SOL"},
            {"Position": "Rewards", "Wert": f"{reward_prefix}{fmt_number(rewards_sol, 5)}", "Einheit": "SOL"},
            {"Position": "JitoSOL/SOL heute", "Wert": fmt_number(portfolio.get("jitosol_sol_ratio"), 6), "Einheit": "Rate"},
        ]
        if portfolio.get("jitosol_sol_ratio_at_start"):
            breakdown.append({
                "Position": "JitoSOL/SOL Start",
                "Wert": fmt_number(portfolio.get("jitosol_sol_ratio_at_start"), 6),
                "Einheit": "Rate",
            })
        if portfolio.get("staking_days"):
            breakdown.append({"Position": "Tage seit Start", "Wert": fmt_number(portfolio.get("staking_days"), 0), "Einheit": "Tage"})
        st.dataframe(pd.DataFrame(breakdown), hide_index=True, use_container_width=True)

        if portfolio.get("staking_basis_source"):
            st.caption(
                "Berechnungsbasis: "
                f"{portfolio.get('staking_basis_source')} · Basis {fmt_number(portfolio.get('staking_basis_sol'), 5)} SOL"
            )


def render_portfolio_tab(live: dict) -> None:
    st.subheader("Login & Portfolio")
    render_auth_box()
    st.divider()

    base_position = load_user_position() if is_logged_in() else PositionSettings()

    with st.form("position_form"):
        st.write("**Portfolio-Einstellungen**")
        wallet_address = st.text_input("Solana Wallet-Adresse (öffentlich)", value=base_position.wallet_address)
        col1, col2 = st.columns(2)
        with col1:
            manual_jito = st.number_input("Manueller JitoSOL-Bestand (Fallback)", min_value=0.0, value=float(base_position.manual_jitosol_amount), step=0.01, format="%.5f")
            avg_entry = st.number_input("Ø Einstieg JitoSOL USD", min_value=0.0, value=float(base_position.avg_entry_jitosol_usd), step=0.01, format="%.2f")
            bought_basis = st.number_input(
                "Phantom Bought / SOL-Basis am Kaufzeitpunkt (optional)",
                min_value=0.0,
                value=float(base_position.bought_sol_basis),
                step=0.01,
                format="%.5f",
                help="Trage hier den Phantom-Wert Bought in SOL ein. Wenn ein Staking-Startdatum gesetzt ist, nutzt die App für den JitoSOL-Zuwachs vorrangig den historischen JitoSOL/SOL-Kurs am Startdatum."
            )
        with col2:
            manual_sol_equiv = st.number_input("Manueller SOL-Gegenwert (Fallback)", min_value=0.0, value=float(base_position.manual_sol_equivalent), step=0.01, format="%.5f")
            hist_sol_entry = st.number_input("Historischer SOL-Einstieg USD", min_value=0.0, value=float(base_position.historical_sol_entry_usd), step=0.01, format="%.2f")
            staking_start = st.text_input(
                "JitoSOL-Kauf-/Startdatum YYYY-MM-DD (optional)",
                value=base_position.staking_start_date,
                help="Wichtig für die korrekte JitoSOL-Ertragsberechnung. Die App vergleicht dann den heutigen JitoSOL/SOL-Kurs mit dem Kurs an diesem Datum."
            )
        submitted = st.form_submit_button("Position speichern")
        position = PositionSettings(wallet_address=wallet_address.strip(), manual_jitosol_amount=manual_jito, manual_sol_equivalent=manual_sol_equiv, avg_entry_jitosol_usd=avg_entry, historical_sol_entry_usd=hist_sol_entry, bought_sol_basis=bought_basis, staking_start_date=staking_start.strip())
        if submitted:
            if is_logged_in():
                if save_user_position(position):
                    st.success("Position gespeichert.")
                    st.cache_data.clear()
            else:
                st.warning("Bitte anmelden, um die Position dauerhaft zu speichern.")

    wallet_summary = cached_wallet(position.wallet_address) if position.wallet_address else {"ok": False}
    portfolio = compute_portfolio(position, wallet_summary, live)

    st.subheader("Portfolio-Auswertung")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Gesamtwert USD", fmt_usd(portfolio["total_usd"]))
    p2.metric("Gesamtwert EUR", fmt_eur(portfolio["total_eur"]))
    p3.metric("JitoSOL", fmt_number(portfolio["jitosol_amount"], 5))
    p4.metric("SOL-Gegenwert", fmt_number(portfolio["sol_equivalent"], 5))

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("JitoSOL/SOL Kurs", fmt_number(portfolio["jitosol_sol_ratio"], 6))
    q2.metric("Buchgewinn USD", fmt_usd(portfolio["pnl_usd"]), fmt_pct(portfolio["pnl_pct"]) if portfolio["cost_basis_usd"] else None)
    q3.metric("JitoSOL-Zuwachs SOL", "n/a" if portfolio["staking_rewards_sol"] is None else fmt_number(portfolio["staking_rewards_sol"], 5))
    q4.metric("JitoSOL-Zuwachs EUR", fmt_eur(portfolio["staking_rewards_eur"]))

    render_staking_rewards_module(portfolio)

    if portfolio.get("staking_basis_source"):
        st.caption(
            "Berechnungsbasis für JitoSOL-Zuwachs: "
            f"{portfolio.get('staking_basis_source')} · Basis: {fmt_number(portfolio.get('staking_basis_sol'), 5)} SOL"
        )
    if portfolio.get("jitosol_sol_ratio_at_start"):
        st.caption(f"JitoSOL/SOL am Startdatum geschätzt: {fmt_number(portfolio.get('jitosol_sol_ratio_at_start'), 6)}")
    if portfolio.get("staking_reward_warning"):
        st.warning(portfolio.get("staking_reward_warning"))

    st.subheader("Performance-Zerlegung")
    breakdown = [
        {"Baustein": "JitoSOL Wert", "USD": fmt_usd(portfolio["jitosol_value_usd"]), "EUR": fmt_eur(portfolio["jitosol_value_eur"])},
        {"Baustein": "Unstaked SOL", "USD": fmt_usd(portfolio["sol_value_usd"]), "EUR": fmt_eur(portfolio["sol_value_eur"])},
        {"Baustein": "USDC", "USD": fmt_usd(portfolio["usdc_balance"]), "EUR": "n/a"},
        {"Baustein": "JitoSOL-Zuwachs", "USD": fmt_usd(portfolio["staking_rewards_usd"]), "EUR": fmt_eur(portfolio["staking_rewards_eur"])},
    ]
    st.dataframe(pd.DataFrame(breakdown), hide_index=True, use_container_width=True)

    if wallet_summary.get("ok"):
        st.caption("Wallet wurde on-chain ausgelesen. Es wurde kein Private Key verwendet.")
        st.write({"SOL": portfolio["sol_balance"], "JitoSOL": portfolio["jitosol_amount"], "USDC": portfolio["usdc_balance"]})
    elif position.wallet_address:
        st.warning(wallet_summary.get("error", "Wallet konnte nicht gelesen werden."))
    if portfolio.get("staking_apy") is not None:
        st.metric("Geschätzte annualisierte JitoSOL-Rendite seit Startdatum", fmt_pct(portfolio["staking_apy"]))


def render_fundamentals_tab(df, latest, prev, result) -> None:
    if latest is None:
        st.warning("Noch keine Fundamentaldaten vorhanden. Starte fetch_data.py oder den GitHub-Workflow.")
        return
    st.subheader("Fundamentaldaten")
    cols = st.columns(4)
    metrics = [
        ("TVL USD", "tvl_usd", fmt_usd),
        ("TVL in SOL", "tvl_sol", lambda v: fmt_number(v, 0)),
        ("Stablecoins Mcap", "stablecoins_usd", fmt_usd),
        ("RWA", "rwa_usd", fmt_usd),
        ("DEX Volumen 24h", "dex_volume_usd", fmt_usd),
        ("App Fees 24h", "app_fees_usd", fmt_usd),
        ("App Revenue 24h", "app_revenue_usd", fmt_usd),
        ("Active Addresses", "active_addresses", lambda v: fmt_number(v, 0)),
    ]
    for idx, (label, key, formatter) in enumerate(metrics):
        delta = pct_delta(latest, prev, key)
        cols[idx % 4].metric(label, formatter(latest.get(key)), None if delta is None else fmt_pct(delta))

    st.subheader("30-Tage-Ampel")
    st.caption("Bestandswerte werden gegen den Stand vor ca. 30 Tagen verglichen. DEX/Fees/Revenue werden als 30D-Rolling-Summe gegen die vorherigen 30 Tage bewertet. Active Addresses werden geglättet.")
    rows = []
    for item in result.get("details", []):
        trend = item.get("trend_pct", item.get("growth_pct"))
        comparison = item.get("comparison") or ("Zu wenig Historie" if trend is None else "30T")
        rows.append({
            "Ampel": traffic_light(trend),
            "Kennzahl": item.get("label"),
            "Score": round(item.get("score", 50), 1),
            "Vergleich": comparison,
            "Veränderung": "Zu wenig Historie" if trend is None else fmt_pct(trend),
            "Gewicht": fmt_pct(item.get("weight", 0) * 100, 0),
            "Bewertung": item.get("note", ""),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_quality_tab(df, latest, live, wallet_summary) -> None:
    st.subheader("Datenqualität")
    rows = build_data_quality_rows(latest, df, live, wallet_summary)
    st.info(quality_summary(rows))
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_thesis_tab(df, latest, result) -> None:
    st.subheader("Warum dieser Score?")
    explanation = score_explanation(result, top_n=8)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Positive Treiber")
        for line in explanation["positive"] or ["Keine klaren positiven Treiber."]:
            st.success(line)
    with col2:
        st.markdown("### Belastungsfaktoren")
        for line in explanation["negative"] or ["Keine starken negativen Treiber."]:
            st.warning(line)

    st.markdown("### Subscores")
    st.dataframe(pd.DataFrame(compute_subscores(result)), hide_index=True, use_container_width=True)

    st.markdown("### These gebrochen?")
    st.caption("Das ist kein automatisches Verkaufssignal, sondern ein Frühwarnsystem für strukturelle Schwächen.")
    st.dataframe(pd.DataFrame(thesis_break_rules(latest, df, result)), hide_index=True, use_container_width=True)


def render_scenario_tab(live: dict, portfolio: dict) -> None:
    st.subheader("Szenario-Rechner")
    st.caption("Berechnet deine SOL/JitoSOL-Exposure in Zielpreis-Szenarien. Es ist eine Modellrechnung, keine Prognose.")
    prefs = load_scenario_preferences() if is_logged_in() else ScenarioPreferences(target_prices_csv=", ".join(str(x) for x in DEFAULT_TARGETS), jitosol_apy_assumption=6.5)
    raw = st.text_input("SOL-Zielpreise USD, kommagetrennt", value=prefs.target_prices_csv)
    apy = st.number_input("JitoSOL APY Annahme", min_value=0.0, max_value=20.0, value=float(prefs.jitosol_apy_assumption), step=0.1)
    if is_logged_in() and st.button("Szenario-Vorgaben speichern"):
        if save_scenario_preferences(ScenarioPreferences(target_prices_csv=raw, jitosol_apy_assumption=apy)):
            st.success("Szenario-Vorgaben gespeichert.")
    try:
        targets = [float(x.strip()) for x in raw.split(",") if x.strip()]
    except Exception:
        targets = DEFAULT_TARGETS
        st.warning("Zielpreise konnten nicht gelesen werden. Verwende Standardwerte.")
    rows = build_price_scenarios(portfolio, live, targets, apy)
    display = []
    for r in rows:
        display.append({
            "SOL Ziel": fmt_usd(r["SOL Ziel USD"]),
            "Portfolio USD": fmt_usd(r["Portfolio USD"]),
            "Portfolio EUR": fmt_eur(r["Portfolio EUR"]),
            "Rewards/Jahr SOL": fmt_number(r["JitoSOL Rewards/Jahr SOL"], 3),
            "Rewards/Jahr USD": fmt_usd(r["Rewards/Jahr USD"]),
            "Abstand zu heute": fmt_pct(r["Abstand zu heute"]) if r["Abstand zu heute"] is not None else "n/a",
        })
    st.dataframe(pd.DataFrame(display), hide_index=True, use_container_width=True)


def render_risk_tab(result: dict, live: dict) -> None:
    st.subheader("Nachkauf- und Hedge-Ampel")
    levels = load_watch_levels() if is_logged_in() else WatchLevels()
    col1, col2 = st.columns(2)
    with col1:
        low = st.number_input("Akkumulation unter USD", min_value=1.0, value=float(levels.accumulation_below_usd), step=5.0)
        warning_below = st.number_input("Warnung unter USD", min_value=1.0, value=float(levels.warning_below_usd), step=5.0)
    with col2:
        high = st.number_input("Hedge prüfen über USD", min_value=1.0, value=float(levels.hedge_check_above_usd), step=5.0)
        profit_above = st.number_input("Teilgewinn prüfen über USD", min_value=1.0, value=float(levels.profit_check_above_usd), step=25.0)
    if is_logged_in() and st.button("Watch-Level speichern"):
        if save_watch_levels(WatchLevels(accumulation_below_usd=low, warning_below_usd=warning_below, hedge_check_above_usd=high, profit_check_above_usd=profit_above, long_term_target_usd=levels.long_term_target_usd)):
            st.success("Watch-Level gespeichert.")
    rows = build_risk_rows(result, live, low, high)
    sol = safe_float(live.get("sol_usd"), 0.0)
    if sol and sol <= warning_below:
        rows.insert(0, {"Bereich": "Warnung unten", "Status": "⚠️ unter persönlichem Warnlevel", "Begründung": f"SOL liegt bei {fmt_usd(sol)} und damit unter {fmt_usd(warning_below)}."})
    if sol and sol >= profit_above:
        rows.append({"Bereich": "Teilgewinnzone", "Status": "🟡 prüfen", "Begründung": f"SOL liegt über deinem Teilgewinn-Level {fmt_usd(profit_above)}."})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Die Ampel kombiniert Kurszone, Score, kurzfristige Marktbewegung und schwache Kennzahlen. Sie ersetzt keine eigene Entscheidung.")


def render_weekly_tab(df, result) -> None:
    st.subheader("Solana Wochenbericht")
    if df.empty:
        st.info("Noch keine Historie vorhanden.")
        return
    rows = weekly_report_rows(df, result)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_coinglass_tab(live: dict) -> None:
    st.subheader("CoinGlass Liquidation Levels")
    st.caption("Benötigt COINGLASS_API_KEY in Streamlit Secrets. Einige Heatmap-Endpunkte sind nur in höheren CoinGlass-Plänen verfügbar.")
    col1, col2, col3, col4 = st.columns(4)
    symbol = col1.text_input("Symbol", DEFAULT_COINGLASS_SYMBOL)
    pair = col2.text_input("Pair", DEFAULT_COINGLASS_PAIR)
    exchange = col3.text_input("Exchange", DEFAULT_COINGLASS_EXCHANGE)
    model = col4.selectbox("Modell", ["aggregated", "pair"], index=0)
    if st.button("Liquidation Levels laden"):
        st.cache_data.clear()
    heatmap = cached_coinglass(symbol, pair, exchange, model)
    if not heatmap.get("ok"):
        st.warning(heatmap.get("message", "Keine CoinGlass-Daten verfügbar."))
        st.link_button("CoinGlass Liquidation Levels öffnen", "https://www.coinglass.com/de/liquidation-levels")
        return
    levels = summarize_liquidation_levels(heatmap, safe_float(live.get("sol_usd"), 0))
    if not levels:
        st.info("API-Antwort erhalten, aber keine Levels konnten extrahiert werden.")
        st.json(heatmap.get("data"))
        return
    st.dataframe(pd.DataFrame(levels), hide_index=True, use_container_width=True)


def _news_signal_tone(classification: str) -> str:
    if "Positiv" in classification:
        return "good"
    if "Risiko" in classification:
        return "bad"
    return "warn"


def render_news_tab() -> None:
    st.subheader("📰 News Radar")
    st.caption("Breiterer News-Feed aus mehreren Solana-Suchclustern: Markt, ETF, RWA, Stablecoins, DeFi, Tech, Reddit.")
    items = cached_news()
    if not items:
        st.info("Aktuell wurden keine News geladen.")
        return

    cats = sorted({str(i.get("category") or "Allgemein") for i in items})
    sources = sorted({str(i.get("source") or "Quelle") for i in items})
    col1, col2, col3, col4 = st.columns([1.15, 1.15, 1.15, 1.55])
    category = col1.selectbox("Kategorie", ["Alle"] + cats, index=0)
    sentiment = col2.selectbox("Signal", ["Alle", "🟢 Positiv", "🟡 Neutral", "🔴 Risiko"], index=0)
    source_filter = col3.selectbox("Quelle", ["Alle"] + sources, index=0)
    query = col4.text_input("Suche", "")

    filtered = []
    q = query.strip().lower()
    for item in items:
        if category != "Alle" and item.get("category") != category:
            continue
        if sentiment != "Alle" and item.get("classification") != sentiment:
            continue
        if source_filter != "Alle" and item.get("source") != source_filter:
            continue
        if q and q not in f"{item.get('title','')} {item.get('summary','')} {item.get('source','')}".lower():
            continue
        filtered.append(item)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artikel geladen", len(items))
    c2.metric("Gefiltert", len(filtered))
    c3.metric("Positiv", sum(1 for i in items if i.get("classification") == "🟢 Positiv"))
    c4.metric("Risiken", sum(1 for i in items if i.get("classification") == "🔴 Risiko"))

    for item in filtered:
        title = str(item.get("title") or "Ohne Titel")
        classification = str(item.get("classification") or "🟡 Neutral")
        category_name = str(item.get("category") or "Allgemein")
        source = str(item.get("source") or "")
        published = str(item.get("published") or "")
        summary = str(item.get("summary") or "")
        link = str(item.get("link") or "")

        with st.container(border=True):
            st.markdown(_badge(classification, _news_signal_tone(classification)), unsafe_allow_html=True)
            st.markdown(f"### {title}")
            st.caption(f"{category_name} · {source} · {published}")
            if summary:
                st.write(summary)
            if link:
                st.link_button("Quelle öffnen", link)


def render_history_tab(df) -> None:
    st.subheader("Historie")
    if df.empty:
        st.info("Noch keine historischen Daten vorhanden.")
        return
    options = {
        "fundamental_score": "Fundamental Score",
        "sol_usd": "SOL/USD",
        "sol_btc": "SOL/BTC",
        "tvl_usd": "TVL USD",
        "tvl_sol": "TVL in SOL",
        "stablecoins_usd": "Stablecoins",
        "rwa_usd": "RWA",
        "dex_volume_usd": "DEX Volumen",
        "app_fees_usd": "App Fees",
        "active_addresses": "Active Addresses",
    }
    available = [k for k in options if k in df.columns]
    choice = st.selectbox("Kennzahl", available, format_func=lambda k: options[k])
    render_line_history(df, choice, options[choice])


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    inject_theme_css()
    inject_ios_pwa_icons()
    render_header()
    render_refresh_controls()
    mode = render_mode_selector()
    df, latest, prev, past, result = get_latest_context()
    live = cached_live_market()
    position, wallet_summary, portfolio = get_portfolio_snapshot(live, mode=mode)
    render_top_metrics(latest, live, result, portfolio, mode)
    if mode == "personal":
        render_onboarding_notice()

    if mode == "personal":
        tab_names = [
            "Übersicht", "Market Intelligence", "News", "Markt", "Market Signals", "Profil & Onboarding", "Portfolio", "Fundamentals", "Datenqualität",
            "These", "Szenarien", "Risiko", "Wochenbericht", "Liquidationen", "Historie", "Rohdaten"
        ]
    else:
        tab_names = [
            "Übersicht", "Market Intelligence", "News", "Markt", "Market Signals", "Fundamentals", "Datenqualität", "These",
            "Szenarien", "Risiko", "Wochenbericht", "Liquidationen", "Historie", "Rohdaten"
        ]
    tabs = st.tabs(tab_names)

    tab_map = dict(zip(tab_names, tabs))
    with tab_map["Übersicht"]:
        render_overview_tab(df, latest, result, live, wallet_summary)
    with tab_map["Market Intelligence"]:
        render_market_intelligence_tab(latest, past, live, portfolio)
    with tab_map["News"]:
        render_news_tab()
    with tab_map["Markt"]:
        render_market_tab(live)
    with tab_map["Market Signals"]:
        render_market_signals_tab(latest, past)
    if "Profil & Onboarding" in tab_map:
        with tab_map["Profil & Onboarding"]:
            render_onboarding_tab(live)
    if "Portfolio" in tab_map:
        with tab_map["Portfolio"]:
            render_portfolio_tab(live)
    with tab_map["Fundamentals"]:
        render_fundamentals_tab(df, latest, prev, result)
    with tab_map["Datenqualität"]:
        render_quality_tab(df, latest, live, wallet_summary)
    with tab_map["These"]:
        render_thesis_tab(df, latest, result)
    with tab_map["Szenarien"]:
        render_scenario_tab(live, portfolio)
    with tab_map["Risiko"]:
        render_risk_tab(result, live)
    with tab_map["Wochenbericht"]:
        render_weekly_tab(df, result)
    with tab_map["Liquidationen"]:
        render_coinglass_tab(live)
    with tab_map["Historie"]:
        render_history_tab(df)
    with tab_map["Rohdaten"]:
        st.subheader("Rohdaten")
        st.dataframe(df.sort_values("snapshot_date", ascending=False) if not df.empty else df, use_container_width=True)


if __name__ == "__main__":
    main()
