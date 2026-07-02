from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from auth import current_user, is_logged_in, load_user_position, render_auth_box, save_user_position
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
from news_fetcher import fetch_news
from portfolio import PositionSettings, compute_portfolio
from scoring import LABELS, WEIGHTS, compute_fundamental_score, interpretation_text, traffic_light
from storage import load_history
from wallet import fetch_wallet_summary

st.set_page_config(page_title=APP_TITLE, page_icon="🟣", layout="wide")


def render_header() -> None:
    logo_col, text_col = st.columns([0.07, 0.93])
    with logo_col:
        st.image(SOLANA_LOGO_URL, width=56)
    with text_col:
        st.title("Solana Research Terminal")
        st.caption("Version 4.0 · Live-Markt, Portfolio, Wallet, Fundamentals, News, Liquidation Levels und Investmentthese")


@st.cache_data(ttl=30, show_spinner=False)
def cached_live_market() -> dict:
    return fetch_live_market()


@st.cache_data(ttl=300, show_spinner=False)
def cached_current_fundamentals() -> dict:
    return fetch_snapshot()


def merge_missing_current_metrics(latest: dict | None) -> dict | None:
    """Use live current API data as fallback when the CSV row still has blanks.

    The historical backfill cannot reliably populate every current UI metric
    (especially RWA and active addresses). This keeps the visible dashboard
    current while the daily CSV catches up.
    """
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
    ]
    for key in fallback_keys:
        if is_missing(enriched.get(key)) and not is_missing(current.get(key)):
            enriched[key] = current.get(key)
    return enriched


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


def pct_delta(latest, prev, key: str) -> float | None:
    if prev is None:
        return None
    try:
        cur = latest.get(key)
        old = prev.get(key)
        if pd.isna(cur) or pd.isna(old) or float(old) == 0:
            return None
        return (float(cur) - float(old)) / float(old) * 100
    except Exception:
        return None


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


def get_latest_context():
    df = load_history(days=3650)
    if df.empty:
        return df, None, None, None, compute_fundamental_score({}, None)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.sort_values("snapshot_date")
    latest_row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    target = latest_row["snapshot_date"] - pd.Timedelta(days=30)
    past_candidates = df[df["snapshot_date"] <= target]
    past = past_candidates.iloc[-1] if not past_candidates.empty else None
    latest = merge_missing_current_metrics(row_to_dict(latest_row))
    result = compute_fundamental_score(latest or {}, row_to_dict(past) if past is not None else None)
    return df, latest, prev, past, result


def render_top_metrics(latest, prev, live: dict, result: dict) -> None:
    score = safe_float(result.get("score"), 50)
    status = result.get("status", "neutral")
    icon = "🟢" if status == "intakt" else "🔴" if status == "geschwaecht" else "🟡"
    sol_usd = safe_float(live.get("sol_usd"), safe_float(latest.get("sol_usd") if latest is not None else None))
    sol_eur = live.get("sol_eur")
    sol_24h = live.get("sol_24h_change")
    btc_dom = latest.get("btc_dominance") if latest is not None else None
    sol_btc = safe_float(live.get("sol_btc"), safe_float(latest.get("sol_btc") if latest is not None else None))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Thesis Status", f"{icon} {str(status).capitalize()}")
    c2.metric("Fundamental Score", f"{score:.0f}/100")
    c3.metric("SOL/USD Live", f"{sol_usd:.2f} $", None if sol_24h is None else fmt_pct(sol_24h) + " 24h")
    c4.metric("SOL/EUR Live", "n/a" if sol_eur is None else f"{float(sol_eur):.2f} €")
    c5.metric("SOL/BTC", f"{sol_btc:.6f}")
    st.progress(max(0, min(int(score), 100)) / 100)
    st.info(interpretation_text(result))
    st.caption(f"Live-Kurs zuletzt abgefragt: {fmt_datetime_utc(live.get('timestamp'))}")


def render_portfolio_panel(live: dict) -> None:
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
        new_position = PositionSettings(wallet_address=wallet_address.strip(), manual_jitosol_amount=manual_jito, manual_sol_equivalent=manual_sol_equiv, avg_entry_jitosol_usd=avg_entry, historical_sol_entry_usd=hist_sol_entry, bought_sol_basis=bought_basis, staking_start_date=staking_start.strip())
        if submitted:
            if is_logged_in():
                if save_user_position(new_position):
                    st.success("Position gespeichert.")
                    st.cache_data.clear()
            else:
                st.warning("Bitte anmelden, um die Position dauerhaft zu speichern.")

    wallet_summary = cached_wallet(new_position.wallet_address) if new_position.wallet_address else {"ok": False}
    portfolio = compute_portfolio(new_position, wallet_summary, live)

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

    if wallet_summary.get("ok"):
        st.caption("Wallet wurde on-chain ausgelesen. Es wurde kein Private Key verwendet.")
        st.write({"SOL": portfolio["sol_balance"], "JitoSOL": portfolio["jitosol_amount"], "USDC": portfolio["usdc_balance"]})
    elif new_position.wallet_address:
        st.warning(wallet_summary.get("error", "Wallet konnte nicht gelesen werden."))
    if portfolio.get("staking_apy") is not None:
        st.metric("Geschätzte annualisierte JitoSOL-Rendite", fmt_pct(portfolio["staking_apy"]))


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
    st.caption("Coinbase begrenzt Kerzenabfragen. Bei kleinen Intervallen kann der dargestellte Zeitraum daher automatisch gekürzt werden.")

    st.divider()
    st.subheader("Live-Markt")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("SOL/USD", fmt_usd(live.get("sol_usd")), None if live.get("sol_24h_change") is None else fmt_pct(live.get("sol_24h_change")) + " 24h")
    m2.metric("SOL/EUR", fmt_eur(live.get("sol_eur")))
    m3.metric("JitoSOL/USD", fmt_usd(live.get("jitosol_usd")), None if live.get("jitosol_24h_change") is None else fmt_pct(live.get("jitosol_24h_change")) + " 24h")
    ratio = safe_float(live.get("jitosol_usd"), 0) / safe_float(live.get("sol_usd"), 1) if live.get("jitosol_usd") and live.get("sol_usd") else None
    m4.metric("JitoSOL/SOL", "n/a" if ratio is None else fmt_number(ratio, 6))


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
        cols[idx % 4].metric(label, formatter(latest.get(key)), None if prev is None else (None if pct_delta(latest, prev, key) is None else fmt_pct(pct_delta(latest, prev, key))))
    st.subheader("30-Tage-Ampel")
    rows = []
    for item in result.get("details", []):
        rows.append({"Ampel": traffic_light(item.get("growth_pct")), "Kennzahl": item.get("label"), "Score": round(item.get("score", 50), 1), "30T": "Zu wenig Historie" if item.get("growth_pct") is None else fmt_pct(item.get("growth_pct")), "Gewicht": fmt_pct(item.get("weight", 0) * 100, 0)})
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
    options = {"fundamental_score": "Fundamental Score", "sol_usd": "SOL/USD", "sol_btc": "SOL/BTC", "tvl_usd": "TVL USD", "tvl_sol": "TVL in SOL", "stablecoins_usd": "Stablecoins", "rwa_usd": "RWA", "dex_volume_usd": "DEX Volumen", "app_fees_usd": "App Fees"}
    available = [k for k in options if k in df.columns]
    choice = st.selectbox("Kennzahl", available, format_func=lambda k: options[k])
    render_line_history(df, choice, options[choice])


def main() -> None:
    render_header()
    df, latest, prev, past, result = get_latest_context()
    live = cached_live_market()
    render_top_metrics(latest, prev, live, result)

    overview, market, portfolio, fundamentals, liquidations, news, history, raw = st.tabs([
        "Übersicht", "Markt", "Portfolio", "Fundamentals", "Liquidationen", "News", "Historie", "Rohdaten"
    ])
    with overview:
        st.subheader("Tageskommentar")
        st.write(interpretation_text(result))
        if latest is not None:
            st.write("Letzter Fundamentaldaten-Snapshot:", str(latest.get("snapshot_date")))
        st.write("Nächste Schritte: CoinGlass API-Key hinterlegen, Wallet speichern, Backfill starten.")
    with market:
        render_market_tab(live)
    with portfolio:
        render_portfolio_panel(live)
    with fundamentals:
        render_fundamentals_tab(df, latest, prev, result)
    with liquidations:
        render_coinglass_tab(live)
    with news:
        render_news_tab()
    with history:
        render_history_tab(df)
    with raw:
        st.subheader("Rohdaten")
        st.dataframe(df.sort_values("snapshot_date", ascending=False) if not df.empty else df, use_container_width=True)


if __name__ == "__main__":
    main()
