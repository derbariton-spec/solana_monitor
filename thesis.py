from __future__ import annotations

from typing import Any

import pandas as pd

from formatting import fmt_pct, safe_float

SUBSCORE_GROUPS = {
    "Fundamentals": ["stablecoins_usd", "rwa_usd", "tvl_usd", "tvl_sol", "dex_volume_usd"],
    "Onchain": ["active_addresses", "chain_fees_usd", "chain_revenue_usd"],
    "Economics": ["app_fees_usd", "app_revenue_usd", "chain_fees_usd", "chain_revenue_usd"],
    "Market Relative": ["sol_btc"],
}


def _detail_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(d.get("key")): d for d in result.get("details", [])}


def compute_subscores(result: dict[str, Any]) -> list[dict[str, Any]]:
    details = _detail_map(result)
    rows: list[dict[str, Any]] = []
    for group, keys in SUBSCORE_GROUPS.items():
        scores = [safe_float(details[k].get("score")) for k in keys if k in details and details[k].get("score") is not None]
        if scores:
            score = sum(scores) / len(scores)
            status = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
            coverage = f"{len(scores)}/{len(keys)}"
            rows.append({"Bereich": group, "Score": round(score, 1), "Status": status, "Daten": coverage})
        else:
            rows.append({"Bereich": group, "Score": None, "Status": "⚪", "Daten": f"0/{len(keys)}"})
    # A simple risk score: high means lower fundamental risk. Penalize red/weak trend items.
    weak = [d for d in result.get("details", []) if safe_float(d.get("score"), 50) < 55]
    risk_score = max(20, min(90, 85 - len(weak) * 8))
    rows.append({"Bereich": "Risk Buffer", "Score": round(risk_score, 1), "Status": "🟢" if risk_score >= 70 else "🟡" if risk_score >= 50 else "🔴", "Daten": f"{len(weak)} Warnsignale"})
    return rows


def score_explanation(result: dict[str, Any], top_n: int = 4) -> dict[str, list[str]]:
    details = result.get("details", [])
    positives = sorted([d for d in details if safe_float(d.get("score"), 0) >= 65], key=lambda x: safe_float(x.get("score")), reverse=True)
    negatives = sorted([d for d in details if safe_float(d.get("score"), 100) < 58], key=lambda x: safe_float(x.get("score")))
    missing = result.get("missing", []) or []

    def line(d: dict[str, Any]) -> str:
        trend = d.get("trend_pct", d.get("growth_pct"))
        trend_text = "" if trend is None else f" ({fmt_pct(trend)})"
        return f"{d.get('label')}: {safe_float(d.get('score')):.0f}/100 · {d.get('note', '')}{trend_text}"

    return {
        "positive": [line(d) for d in positives[:top_n]],
        "negative": [line(d) for d in negatives[:top_n]],
        "missing": [str(m) for m in missing[:top_n]],
    }


def _change_since_days(df: pd.DataFrame | None, key: str, days: int) -> float | None:
    if df is None or df.empty or key not in df.columns or "snapshot_date" not in df.columns:
        return None
    tmp = df[["snapshot_date", key]].copy()
    tmp["snapshot_date"] = pd.to_datetime(tmp["snapshot_date"], errors="coerce")
    tmp[key] = pd.to_numeric(tmp[key], errors="coerce")
    tmp = tmp.dropna(subset=["snapshot_date", key]).sort_values("snapshot_date")
    if tmp.empty:
        return None
    latest = tmp.iloc[-1]
    target = latest["snapshot_date"] - pd.Timedelta(days=days)
    past = tmp[tmp["snapshot_date"] <= target]
    if past.empty:
        return None
    old = float(past.iloc[-1][key])
    if old == 0:
        return None
    return (float(latest[key]) - old) / old * 100


def thesis_break_rules(latest: dict[str, Any] | None, df: pd.DataFrame | None, result: dict[str, Any]) -> list[dict[str, str]]:
    latest = latest or {}
    rules: list[tuple[str, str, float | None, float]] = [
        ("Stablecoins fallen 90T", "stablecoins_usd", _change_since_days(df, "stablecoins_usd", 90), -5.0),
        ("TVL USD fällt stark 90T", "tvl_usd", _change_since_days(df, "tvl_usd", 90), -20.0),
        ("TVL in SOL fällt stark 90T", "tvl_sol", _change_since_days(df, "tvl_sol", 90), -20.0),
        ("SOL/BTC verliert 90T", "sol_btc", _change_since_days(df, "sol_btc", 90), -15.0),
        ("DEX Volumen schwach 90T", "dex_volume_usd", _change_since_days(df, "dex_volume_usd", 90), -25.0),
    ]
    rows: list[dict[str, str]] = []
    for title, _key, change, threshold in rules:
        if change is None:
            rows.append({"Status": "⚪", "Kriterium": title, "Befund": "zu wenig Historie"})
        elif change <= threshold:
            rows.append({"Status": "🔴", "Kriterium": title, "Befund": f"{fmt_pct(change)} · unter Schwelle {fmt_pct(threshold)}"})
        elif change <= threshold / 2:
            rows.append({"Status": "🟡", "Kriterium": title, "Befund": f"{fmt_pct(change)} · beobachten"})
        else:
            rows.append({"Status": "🟢", "Kriterium": title, "Befund": f"{fmt_pct(change)} · unkritisch"})

    rwa = latest.get("rwa_usd")
    if rwa is None or pd.isna(rwa):
        rows.append({"Status": "⚪", "Kriterium": "RWA-Daten verfügbar", "Befund": "aktueller RWA-Wert fehlt"})
    elif safe_float(rwa) < 500_000_000:
        rows.append({"Status": "🔴", "Kriterium": "RWA strukturell relevant", "Befund": "unter 500 Mio. USD"})
    else:
        rows.append({"Status": "🟢", "Kriterium": "RWA strukturell relevant", "Befund": "aktuell über Mindestschwelle"})

    if safe_float(result.get("score"), 50) < 45:
        rows.append({"Status": "🔴", "Kriterium": "Gesamtscore", "Befund": "These wirkt geschwächt"})
    else:
        rows.append({"Status": "🟢", "Kriterium": "Gesamtscore", "Befund": "keine Score-Bruchmarke"})
    return rows
