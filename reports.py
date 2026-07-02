from __future__ import annotations

from typing import Any

import pandas as pd

from formatting import fmt_pct, safe_float

REPORT_KEYS = {
    "sol_usd": "SOL/USD",
    "sol_btc": "SOL/BTC",
    "tvl_usd": "TVL USD",
    "stablecoins_usd": "Stablecoins",
    "rwa_usd": "RWA",
    "dex_volume_usd": "DEX Volumen",
    "app_fees_usd": "App Fees",
    "active_addresses": "Active Addresses",
}


def _week_change(df: pd.DataFrame, key: str) -> float | None:
    if df is None or df.empty or key not in df.columns or "snapshot_date" not in df.columns:
        return None
    tmp = df[["snapshot_date", key]].copy()
    tmp["snapshot_date"] = pd.to_datetime(tmp["snapshot_date"], errors="coerce")
    tmp[key] = pd.to_numeric(tmp[key], errors="coerce")
    tmp = tmp.dropna().sort_values("snapshot_date")
    if tmp.empty:
        return None
    latest = tmp.iloc[-1]
    target = latest["snapshot_date"] - pd.Timedelta(days=7)
    past = tmp[tmp["snapshot_date"] <= target]
    if past.empty:
        return None
    old = safe_float(past.iloc[-1][key], 0.0)
    if old == 0:
        return None
    return (safe_float(latest[key]) - old) / old * 100


def weekly_report_rows(df: pd.DataFrame, result: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, label in REPORT_KEYS.items():
        change = _week_change(df, key)
        if change is None:
            status = "⚪"
            text = "zu wenig Historie"
        elif change >= 5:
            status = "🟢"
            text = fmt_pct(change)
        elif change >= -5:
            status = "🟡"
            text = fmt_pct(change)
        else:
            status = "🔴"
            text = fmt_pct(change)
        rows.append({"Status": status, "Kennzahl": label, "7 Tage": text})
    score = safe_float(result.get("score"), 50.0)
    if score >= 65:
        conclusion = "These in dieser Datenlage intakt."
        status = "🟢"
    elif score < 45:
        conclusion = "These geschwächt, rote Kennzahlen prüfen."
        status = "🔴"
    else:
        conclusion = "Gemischte Datenlage, weiter beobachten."
        status = "🟡"
    rows.append({"Status": status, "Kennzahl": "Wochenfazit", "7 Tage": conclusion})
    return rows
