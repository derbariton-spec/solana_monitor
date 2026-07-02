from __future__ import annotations

from typing import Any

import pandas as pd

from config import has_coinglass, has_supabase
from formatting import is_missing


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


def quality_summary(rows: list[dict[str, Any]]) -> str:
    hard_missing = [r["Datenpunkt"] for r in rows if r.get("Status") == "❌"]
    warnings = [r["Datenpunkt"] for r in rows if r.get("Status") in {"⚠️", "🟡"}]
    if not hard_missing and not warnings:
        return "Datenqualität sehr gut. Der Score ist gut belastbar."
    if hard_missing:
        return "Achtung: wichtige Daten fehlen noch: " + ", ".join(hard_missing[:5]) + "."
    return "Datenqualität grundsätzlich brauchbar, aber mit Einschränkungen bei: " + ", ".join(warnings[:6]) + "."
