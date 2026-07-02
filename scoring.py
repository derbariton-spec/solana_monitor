from __future__ import annotations

from typing import Any

from formatting import safe_float

LABELS = {
    "tvl_usd": "TVL USD",
    "tvl_sol": "TVL in SOL",
    "stablecoins_usd": "Stablecoins Mcap",
    "rwa_usd": "RWA Active Mcap",
    "dex_volume_usd": "DEX Volumen",
    "app_fees_usd": "App Fees",
    "app_revenue_usd": "App Revenue",
    "chain_fees_usd": "Chain Fees",
    "chain_revenue_usd": "Chain Revenue",
    "active_addresses": "Active Addresses",
    "sol_btc": "SOL/BTC",
}

# V4.1 scoring: structural Solana thesis, not short-term trading signal.
# Missing optional metrics are excluded. Available metrics are scored by a mix of
# absolute strength and 30-day trend.
WEIGHTS = {
    "stablecoins_usd": 0.17,
    "rwa_usd": 0.14,
    "tvl_usd": 0.13,
    "tvl_sol": 0.10,
    "dex_volume_usd": 0.11,
    "app_fees_usd": 0.10,
    "app_revenue_usd": 0.07,
    "chain_fees_usd": 0.07,
    "active_addresses": 0.07,
    "sol_btc": 0.04,
}

ABSOLUTE_THRESHOLDS = {
    "stablecoins_usd": (5_000_000_000, 12_000_000_000),
    "rwa_usd": (500_000_000, 1_500_000_000),
    "tvl_usd": (2_000_000_000, 5_000_000_000),
    "dex_volume_usd": (500_000_000, 2_000_000_000),
    "app_fees_usd": (1_000_000, 5_000_000),
    "app_revenue_usd": (250_000, 2_000_000),
    "chain_fees_usd": (150_000, 500_000),
    "active_addresses": (500_000, 2_500_000),
}


def growth_pct(current: dict[str, Any], past: dict[str, Any] | None, key: str) -> float | None:
    if not past:
        return None
    cur = current.get(key)
    old = past.get(key)
    if cur is None or old is None:
        return None
    old_f = safe_float(old, 0)
    if old_f == 0:
        return None
    return (safe_float(cur) - old_f) / old_f * 100


def absolute_score(key: str, value: Any) -> float | None:
    if value is None or key not in ABSOLUTE_THRESHOLDS:
        return None
    low, high = ABSOLUTE_THRESHOLDS[key]
    value = safe_float(value)
    if value <= low:
        return 40
    if value >= high:
        return 86
    return 40 + (value - low) / (high - low) * 46


def growth_score(g: float | None) -> float | None:
    if g is None:
        return None
    if g >= 20:
        return 92
    if g >= 8:
        return 82
    if g >= 0:
        return 68
    if g >= -5:
        return 56
    if g >= -15:
        return 42
    return 25


def growth_note(g: float | None) -> str:
    if g is None:
        return "absolut bewertet"
    if g >= 20:
        return "stark verbessert"
    if g >= 8:
        return "verbessert"
    if g >= 0:
        return "leicht verbessert"
    if g >= -5:
        return "stabil bis leicht schwächer"
    if g >= -15:
        return "schwächer"
    return "deutlich schwächer"


def metric_score(key: str, current: dict[str, Any], past: dict[str, Any] | None) -> tuple[float | None, float | None, str]:
    value = current.get(key)
    if value is None:
        return None, None, "nicht verfügbar"

    g = growth_pct(current, past, key)
    g_score = growth_score(g)
    a_score = absolute_score(key, value)

    if g_score is not None and a_score is not None:
        # Long-term fundamental thesis: absolute adoption matters slightly more than 30d momentum.
        score = 0.60 * a_score + 0.40 * g_score
        return score, g, f"{growth_note(g)} · strukturell bewertet"
    if a_score is not None:
        return a_score, g, "absolut bewertet"
    if g_score is not None:
        return g_score, g, growth_note(g)
    return 50, None, "neutral"


def compute_fundamental_score(current: dict[str, Any], past: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = []
    weighted = 0.0
    used = 0.0
    missing = []
    for key, weight in WEIGHTS.items():
        score, g, note = metric_score(key, current, past)
        if score is None:
            missing.append(key)
            continue
        rows.append({"key": key, "label": LABELS.get(key, key), "score": score, "growth_pct": g, "note": note, "weight": weight})
        weighted += score * weight
        used += weight
    final = weighted / used if used else 50.0
    if final >= 65:
        status = "intakt"
    elif final < 45:
        status = "geschwaecht"
    else:
        status = "neutral"
    return {
        "score": round(final, 2),
        "status": status,
        "details": rows,
        "missing": missing,
        "coverage": round(used / sum(WEIGHTS.values()) * 100, 1) if WEIGHTS else 0,
        "growth_pct": {r["key"]: r["growth_pct"] for r in rows},
    }


def traffic_light(value: float | None) -> str:
    if value is None:
        return "⚪"
    if value >= 8:
        return "🟢"
    if value >= -5:
        return "🟡"
    return "🔴"


def interpretation_text(result: dict[str, Any]) -> str:
    score = safe_float(result.get("score"), 50)
    status = result.get("status", "neutral")
    coverage = result.get("coverage")
    suffix = f" Datenabdeckung: {coverage:.0f}%." if isinstance(coverage, (int, float)) else ""
    if status == "intakt":
        return f"Score {score:.0f}/100: Die Solana-These wirkt auf Basis der verfügbaren Fundamentaldaten intakt.{suffix}"
    if status == "geschwaecht":
        return f"Score {score:.0f}/100: Die Solana-These wirkt geschwächt. Prüfe die roten Kennzahlen im Detail.{suffix}"
    return f"Score {score:.0f}/100: Die Datenlage ist gemischt oder noch unvollständig.{suffix}"
