from __future__ import annotations

import pandas as pd
import streamlit as st

from auth import is_logged_in, load_user_position, render_auth_box, save_user_position
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
from market_signals import build_market_signal_report, signal_rows
from news_fetcher import fetch_news
from portfolio import PositionSettings, compute_portfolio
from quality import build_data_quality_rows, quality_summary
from reports import weekly_report_rows
from risk import build_risk_rows
from scenario import DEFAULT_TARGETS, build_price_scenarios
from scoring import compute_fundamental_score, interpretation_text, traffic_light
from storage import load_history
from thesis import compute_subscores, score_explanation, thesis_break_rules
from wallet import fetch_wallet_summary

st.set_page_config(page_title=APP_TITLE, page_icon="🟣", layout="wide")


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
    return fetch_news(max_items_per_feed=4)


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


def get_portfolio_snapshot(live: dict):
    position = load_user_position() if is_logged_in() else PositionSettings()
    wallet_summary = cached_wallet(position.wallet_address) if position.wallet_address else {"ok": False, "error": "Keine Wallet hinterlegt."}
    portfolio = compute_portfolio(position, wallet_summary, live)
    return position, wallet_summary, portfolio


# -----------------------------
# Header and top metrics
# -----------------------------

def render_header() -> None:
    logo_col, text_col = st.columns([0.07, 0.93])
    with logo_col:
        st.image(SOLANA_LOGO_URL, width=56)
    with text_col:
        st.title("Solana Research Terminal")
        st.caption(f"Version {APP_VERSION} · Score-Erklärung, Datenqualität, Subscores, Wallet/JitoSOL, Szenarien, Risiko, Market Signals und Liquidation Levels")


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


def render_top_metrics(latest, live: dict, result: dict) -> None:
    score = safe_float(result.get("score"), 50)
    status = result.get("status", "neutral")
    icon = "🟢" if status == "intakt" else "🔴" if status == "geschwaecht" else "🟡"
    sol_usd = safe_float(live.get("sol_usd"), safe_float(latest.get("sol_usd") if latest is not None else None))
    sol_eur = live.get("sol_eur")
    sol_24h = live.get("sol_24h_change")
    sol_btc = safe_float(live.get("sol_btc"), safe_float(latest.get("sol_btc") if latest is not None else None))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Thesis Status", f"{icon} {str(status).capitalize()}")
    c2.metric("Gesamt Score", f"{score:.0f}/100")
    c3.metric("SOL/USD Live", f"{sol_usd:.2f} $", None if sol_24h is None else fmt_pct(sol_24h) + " 24h")
    c4.metric("SOL/EUR Live", "n/a" if sol_eur is None else f"{float(sol_eur):.2f} €")
    c5.metric("SOL/BTC", f"{sol_btc:.6f}")
    st.progress(max(0, min(int(score), 100)) / 100)
    st.info(interpretation_text(result))
    st.caption(f"Live-Kurs zuletzt abgefragt: {fmt_datetime_utc(live.get('timestamp'))}")


# -----------------------------
# Individual tabs
# -----------------------------

def render_overview_tab(df, latest, result, live, wallet_summary) -> None:
    st.subheader("Tageskommentar")
    st.write(interpretation_text(result))

    st.subheader("Subscores")
    sub = pd.DataFrame(compute_subscores(result))
    st.dataframe(sub, hide_index=True, use_container_width=True)

    explanation = score_explanation(result)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Positive Treiber**")
        if explanation["positive"]:
            for line in explanation["positive"]:
                st.success(line)
        else:
            st.info("Noch keine klaren positiven Treiber.")
    with col2:
        st.markdown("**Belastungsfaktoren**")
        if explanation["negative"]:
            for line in explanation["negative"]:
                st.warning(line)
        else:
            st.success("Keine starken negativen Treiber im Score.")
    with col3:
        st.markdown("**Datenabdeckung**")
        quality_rows = build_data_quality_rows(latest, df, live, wallet_summary)
        st.write(quality_summary(quality_rows))
        if latest is not None:
            st.caption(f"Letzter Fundamentaldaten-Snapshot: {latest.get('snapshot_date')}")

    st.subheader("These gebrochen?")
    st.dataframe(pd.DataFrame(thesis_break_rules(latest, df, result)), hide_index=True, use_container_width=True)


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
            bought_basis = st.number_input("Bought / ursprünglich gestakte SOL-Basis", min_value=0.0, value=float(base_position.bought_sol_basis), step=0.01, format="%.5f")
        with col2:
            manual_sol_equiv = st.number_input("Manueller SOL-Gegenwert (Fallback)", min_value=0.0, value=float(base_position.manual_sol_equivalent), step=0.01, format="%.5f")
            hist_sol_entry = st.number_input("Historischer SOL-Einstieg USD", min_value=0.0, value=float(base_position.historical_sol_entry_usd), step=0.01, format="%.2f")
            staking_start = st.text_input("Staking-Startdatum YYYY-MM-DD (optional)", value=base_position.staking_start_date)
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
    q3.metric("Staking-Ertrag SOL", "n/a" if portfolio["staking_rewards_sol"] is None else fmt_number(portfolio["staking_rewards_sol"], 5))
    q4.metric("Staking-Ertrag EUR", fmt_eur(portfolio["staking_rewards_eur"]))

    st.subheader("Performance-Zerlegung")
    breakdown = [
        {"Baustein": "JitoSOL Wert", "USD": fmt_usd(portfolio["jitosol_value_usd"]), "EUR": fmt_eur(portfolio["jitosol_value_eur"])},
        {"Baustein": "Unstaked SOL", "USD": fmt_usd(portfolio["sol_value_usd"]), "EUR": fmt_eur(portfolio["sol_value_eur"])},
        {"Baustein": "USDC", "USD": fmt_usd(portfolio["usdc_balance"]), "EUR": "n/a"},
        {"Baustein": "JitoSOL Rewards", "USD": fmt_usd(portfolio["staking_rewards_usd"]), "EUR": fmt_eur(portfolio["staking_rewards_eur"])},
    ]
    st.dataframe(pd.DataFrame(breakdown), hide_index=True, use_container_width=True)

    if wallet_summary.get("ok"):
        st.caption("Wallet wurde on-chain ausgelesen. Es wurde kein Private Key verwendet.")
        st.write({"SOL": portfolio["sol_balance"], "JitoSOL": portfolio["jitosol_amount"], "USDC": portfolio["usdc_balance"]})
    elif position.wallet_address:
        st.warning(wallet_summary.get("error", "Wallet konnte nicht gelesen werden."))
    if portfolio.get("staking_apy") is not None:
        st.metric("Geschätzte annualisierte JitoSOL-Rendite", fmt_pct(portfolio["staking_apy"]))


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
    default_targets = ", ".join(str(x) for x in DEFAULT_TARGETS)
    raw = st.text_input("SOL-Zielpreise USD, kommagetrennt", value=default_targets)
    apy = st.number_input("JitoSOL APY Annahme", min_value=0.0, max_value=20.0, value=6.5, step=0.1)
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
    col1, col2 = st.columns(2)
    with col1:
        low = st.number_input("Akkumulation unter USD", min_value=1.0, value=150.0, step=5.0)
    with col2:
        high = st.number_input("Vorsicht über USD", min_value=1.0, value=220.0, step=5.0)
    st.dataframe(pd.DataFrame(build_risk_rows(result, live, low, high)), hide_index=True, use_container_width=True)
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


def render_news_tab() -> None:
    st.subheader("News & Reddit")
    for item in cached_news():
        box = st.success if "🟢" in item.get("classification", "") else st.error if "🔴" in item.get("classification", "") else st.info
        box(f"{item.get('classification')} – {item.get('title')}")
        st.caption(f"{item.get('source')} · {item.get('published')}")
        if item.get("link"):
            st.markdown(f"[Quelle öffnen]({item['link']})")
        st.divider()


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
    render_header()
    render_refresh_controls()
    df, latest, prev, past, result = get_latest_context()
    live = cached_live_market()
    position, wallet_summary, portfolio = get_portfolio_snapshot(live)
    render_top_metrics(latest, live, result)

    tabs = st.tabs([
        "Übersicht",
        "Markt",
        "Market Signals",
        "Portfolio",
        "Fundamentals",
        "Datenqualität",
        "These",
        "Szenarien",
        "Risiko",
        "Wochenbericht",
        "Liquidationen",
        "News",
        "Historie",
        "Rohdaten",
    ])

    with tabs[0]:
        render_overview_tab(df, latest, result, live, wallet_summary)
    with tabs[1]:
        render_market_tab(live)
    with tabs[2]:
        render_market_signals_tab(latest, past)
    with tabs[3]:
        render_portfolio_tab(live)
    with tabs[4]:
        render_fundamentals_tab(df, latest, prev, result)
    with tabs[5]:
        render_quality_tab(df, latest, live, wallet_summary)
    with tabs[6]:
        render_thesis_tab(df, latest, result)
    with tabs[7]:
        render_scenario_tab(live, portfolio)
    with tabs[8]:
        render_risk_tab(result, live)
    with tabs[9]:
        render_weekly_tab(df, result)
    with tabs[10]:
        render_coinglass_tab(live)
    with tabs[11]:
        render_news_tab()
    with tabs[12]:
        render_history_tab(df)
    with tabs[13]:
        st.subheader("Rohdaten")
        st.dataframe(df.sort_values("snapshot_date", ascending=False) if not df.empty else df, use_container_width=True)


if __name__ == "__main__":
    main()
