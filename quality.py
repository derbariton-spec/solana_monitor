from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from config import has_coinglass, has_supabase
from formatting import is_missing, safe_float


CORE_METRICS = {
    "sol_usd": "SOL Preis",
    "tvl_usd": "TVL",
    "stablecoins_usd": "Stablecoins",
    "rwa_usd": "RWA Active Mcap",
    "dex_volume_usd": "DEX Volumen",
    "app_fees_usd": "App Fees",
    "app_revenue_usd": "App Revenue",
    "chain_fees_usd": "Chain Fees",
    "active_addresses": "Active Addresses",
    "sol_btc": "SOL/BTC",
}


IMPORTANT_FOR_SCORE = {
    "tvl_usd",
    "stablecoins_usd",
    "rwa_usd",
    "dex_volume_usd",
    "app_fees_usd",
    "active_addresses",
    "sol_btc",
}


def _history_points(df: pd.DataFrame | None, key: str) -> int:
    if df is None or df.empty or key not in df.columns:
        return 0
    values = pd.to_numeric(df[key], errors="coerce").dropna()
    return int(len(values))


def _last_age_text(df: pd.DataFrame | None) -> str:
    if df is None or df.empty or "snapshot_date" not in df.columns:
        return "keine Historie"
    dates = pd.to_datetime(df["snapshot_date"], errors="coerce").dropna()
    if dates.empty:
        return "kein gültiges Datum"
    latest = dates.max().date()
    return f"letzter Snapshot: {latest.isoformat()}"


def _latest_snapshot_info(df: pd.DataFrame | None) -> tuple[dt.date | None, int | None]:
    if df is None or df.empty or "snapshot_date" not in df.columns:
        return None, None
    dates = pd.to_datetime(df["snapshot_date"], errors="coerce").dropna()
    if dates.empty:
        return None, None
    latest_date = dates.max().date()
    age_days = max(0, (dt.datetime.now(dt.timezone.utc).date() - latest_date).days)
    return latest_date, age_days


def _source_status(ok: bool, warning: bool = False) -> str:
    if ok:
        return "✅ aktiv"
    if warning:
        return "⚠️ prüfen"
    return "❌ fehlt"


def _age_text(latest_date: dt.date | None, age_days: int | None) -> str:
    if latest_date is None:
        return "kein gültiger Stand"
    if age_days is None:
        return latest_date.isoformat()
    return f"{latest_date.isoformat()} ({age_days} Tage alt)"


def _live_age_text(value: Any) -> str:
    if isinstance(value, dt.datetime):
        loaded = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - loaded.astimezone(dt.timezone.utc)
        minutes = max(0, int(age.total_seconds() // 60))
        return f"{loaded.strftime('%Y-%m-%d %H:%M UTC')} ({minutes} Min. alt)"
    return "aktueller App-Cache"


def _row(status: str, source: str, area: str, stand: str, mode: str, note: str) -> dict[str, str]:
    return {
        "Status": status,
        "Quelle": source,
        "Bereich": area,
        "Stand": stand,
        "Modus": mode,
        "Hinweis": note,
    }


def build_data_quality_rows(latest: dict[str, Any] | None, df: pd.DataFrame | None, live: dict[str, Any] | None = None, wallet_summary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    latest = latest or {}
    live = live or {}
    rows: list[dict[str, Any]] = []

    for key, label in CORE_METRICS.items():
        present = not is_missing(latest.get(key)) or not is_missing(live.get(key))
        points = _history_points(df, key)
        if present and points >= 60:
            status = "✅"
            quality = "gut"
        elif present and points >= 5:
            status = "🟡"
            quality = "kurze Historie"
        elif present:
            status = "⚠️"
            quality = "nur aktueller Wert"
        else:
            status = "❌" if key in IMPORTANT_FOR_SCORE else "⚪"
            quality = "fehlt"
        rows.append({
            "Status": status,
            "Datenpunkt": label,
            "Qualität": quality,
            "Historie": points,
            "Hinweis": _last_age_text(df) if key == "sol_usd" else "",
        })

    rows.append({
        "Status": "✅" if df is not None and not df.empty and len(df) >= 365 else "🟡" if df is not None and not df.empty else "❌",
        "Datenpunkt": "Backfill",
        "Qualität": "mehrjährig" if df is not None and len(df) >= 1000 else "vorhanden" if df is not None and not df.empty else "fehlt",
        "Historie": 0 if df is None else len(df),
        "Hinweis": _last_age_text(df),
    })
    rows.append({
        "Status": "✅" if has_supabase() else "⚠️",
        "Datenpunkt": "Supabase Login",
        "Qualität": "konfiguriert" if has_supabase() else "nicht konfiguriert",
        "Historie": "",
        "Hinweis": "Portfolio-Speicherung" if has_supabase() else "SUPABASE_URL und SUPABASE_ANON_KEY fehlen",
    })
    rows.append({
        "Status": "✅" if has_coinglass() else "⚠️",
        "Datenpunkt": "CoinGlass",
        "Qualität": "API-Key vorhanden" if has_coinglass() else "optional",
        "Historie": "",
        "Hinweis": "Liquidation Levels aktiv" if has_coinglass() else "COINGLASS_API_KEY fehlt",
    })
    if wallet_summary:
        rows.append({
            "Status": "✅" if wallet_summary.get("ok") else "⚠️",
            "Datenpunkt": "Wallet RPC",
            "Qualität": "on-chain gelesen" if wallet_summary.get("ok") else "Fallback/Fehler",
            "Historie": "",
            "Hinweis": wallet_summary.get("error") or "öffentliche Wallet-Adresse ausgelesen",
        })
    return rows


def build_source_status_rows(
    latest: dict[str, Any] | None,
    df: pd.DataFrame | None,
    live: dict[str, Any] | None = None,
    news_impact: dict[str, Any] | None = None,
    macro_data: dict[str, Any] | None = None,
    wallet_summary: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    latest = latest or {}
    live = live or {}
    news_impact = news_impact or {}
    macro_data = macro_data or {}
    wallet_summary = wallet_summary or {}
    rows: list[dict[str, str]] = []

    latest_date, age_days = _latest_snapshot_info(df)
    if latest_date is None:
        history_status = "❌ fehlt"
        history_note = "keine lokale Historie gefunden"
    elif age_days is not None and age_days <= 1:
        history_status = "✅ aktuell"
        history_note = f"{len(df) if df is not None else 0} Snapshots lokal verfügbar"
    elif age_days is not None and age_days <= 3:
        history_status = "⚠️ prüfen"
        history_note = "Fundamentaldaten sind leicht veraltet"
    else:
        history_status = "❌ veraltet"
        history_note = "automatischen Update-Lauf prüfen"
    rows.append(_row(
        history_status,
        "Lokale Historie",
        "Fundamentaldaten / Score-Basis",
        _age_text(latest_date, age_days),
        "CSV / lokaler Speicher",
        history_note,
    ))

    has_prices = not is_missing(live.get("sol_usd")) and not is_missing(live.get("sol_btc"))
    rows.append(_row(
        _source_status(has_prices),
        "CoinGecko",
        "SOL, JitoSOL, BTC, USD/EUR",
        _live_age_text(live.get("timestamp")),
        "Live API mit 30-Sekunden Cache",
        "Preise aktiv" if has_prices else "Live-Kurse nicht verfügbar",
    ))

    defi_keys = ("tvl_usd", "stablecoins_usd", "dex_volume_usd", "app_fees_usd", "app_revenue_usd")
    defi_count = sum(1 for key in defi_keys if not is_missing(latest.get(key)))
    rows.append(_row(
        _source_status(defi_count >= 4, warning=defi_count > 0),
        "DefiLlama / Fundamentaldaten",
        "TVL, Stablecoins, DEX, Fees, Revenue",
        _age_text(latest_date, age_days),
        "Snapshot + Live-Fallback",
        f"{defi_count}/{len(defi_keys)} Kernwerte vorhanden",
    ))

    score = safe_float(news_impact.get("score"), None)
    articles = int(safe_float(news_impact.get("positive_count"), 0) or 0) + int(safe_float(news_impact.get("risk_count"), 0) or 0)
    has_reasons = bool(news_impact.get("reasons_positive") or news_impact.get("reasons_risk"))
    if score is not None:
        news_status = "✅ aktiv" if articles > 0 or has_reasons else "⚠️ prüfen"
        news_note = f"Impact {score:.0f}/100 · {news_impact.get('label', 'neutral')}"
    else:
        news_status = "⚠️ prüfen"
        news_note = "News Impact konnte nicht berechnet werden"
    rows.append(_row(
        news_status,
        "News-Feeds inkl. Kryptovergleich",
        "News Impact Score",
        "5-Minuten Cache",
        "RSS / Feedparser / Artikelgewichtung",
        news_note,
    ))

    macro_rows = macro_data.get("rows") or []
    yahoo_rows = [r for r in macro_rows if "yahoo" in str(r.get("Quelle", "")).lower()]
    macro_ok = bool(macro_rows) and any(str(r.get("Wert", "n/a")).lower() != "n/a" for r in macro_rows)
    rows.append(_row(
        _source_status(macro_ok),
        "Yahoo Finance / Macro",
        "BTC, Aktien, VIX, Dollar, Renditen, Gold, Öl",
        str(macro_data.get("updated_at") or "Macro-Cache"),
        "Parallele Live-Abfrage",
        f"{len(yahoo_rows)} Yahoo-Layer aktiv, {len(macro_rows)} Macro-Layer gesamt",
    ))

    cpi_row = next((r for r in macro_rows if str(r.get("Layer", "")).lower() == "us cpi yoy"), {})
    cpi_ok = bool(cpi_row) and str(cpi_row.get("Wert", "n/a")).lower() != "n/a"
    rows.append(_row(
        _source_status(cpi_ok, warning=bool(cpi_row)),
        "BLS",
        "US CPI / Inflation",
        str(cpi_row.get("Stand") or "Monatswert"),
        "Public API",
        str(cpi_row.get("Lesart") or "Inflationsdaten prüfen"),
    ))

    geo = macro_data.get("geopolitics") or {}
    geo_news = macro_data.get("news") or []
    rows.append(_row(
        _source_status(bool(geo_news), warning=bool(geo)),
        "Google News Macro",
        "Geopolitik / Öl / Fed-Risiko",
        str(macro_data.get("updated_at") or "Macro-Cache"),
        "RSS News-Scan",
        f"{geo.get('status', 'n/a')} · {geo.get('risk_hits', 0)} Risiko-Treffer",
    ))

    rows.append(_row(
        "✅ aktiv" if has_supabase() else "⚠️ optional",
        "Supabase",
        "Login / Portfolio-Speicherung",
        "App-Konfiguration",
        "Cloud-Speicher",
        "konfiguriert" if has_supabase() else "nicht konfiguriert; Portfolio bleibt lokal in der Session",
    ))

    rows.append(_row(
        "✅ aktiv" if has_coinglass() else "⚠️ optional",
        "CoinGlass",
        "Open Interest / Liquidation Levels",
        "App-Konfiguration",
        "API-Key",
        "API-Key vorhanden" if has_coinglass() else "optional; COINGLASS_API_KEY fehlt",
    ))

    if wallet_summary:
        wallet_ok = bool(wallet_summary.get("ok"))
        rows.append(_row(
            _source_status(wallet_ok, warning=True),
            "Solana Wallet RPC",
            "On-chain Wallet-Bestand",
            "Live bei Seitenaufruf",
            "Public RPC / Fallback",
            "Wallet gelesen" if wallet_ok else str(wallet_summary.get("error") or "Wallet nicht aktiv"),
        ))

    return rows


def source_status_summary(rows: list[dict[str, str]]) -> str:
    broken = [r["Quelle"] for r in rows if str(r.get("Status", "")).startswith("❌")]
    warnings = [r["Quelle"] for r in rows if str(r.get("Status", "")).startswith("⚠️")]
    if broken:
        return "Quellen prüfen: kritische Datenquelle betroffen: " + ", ".join(broken[:4]) + "."
    if warnings:
        return "Quellenstatus brauchbar, aber mit optionalen oder eingeschränkten Quellen: " + ", ".join(warnings[:5]) + "."
    return "Alle wichtigen Quellen sind aktiv und aktuell."


def quality_summary(rows: list[dict[str, Any]]) -> str:
    hard_missing = [r["Datenpunkt"] for r in rows if r.get("Status") == "❌"]
    warnings = [r["Datenpunkt"] for r in rows if r.get("Status") in {"⚠️", "🟡"}]
    if not hard_missing and not warnings:
        return "Datenqualität sehr gut. Der Score ist gut belastbar."
    if hard_missing:
        return "Achtung: wichtige Daten fehlen noch: " + ", ".join(hard_missing[:5]) + "."
    return "Datenqualität grundsätzlich brauchbar, aber mit Einschränkungen bei: " + ", ".join(warnings[:6]) + "."
