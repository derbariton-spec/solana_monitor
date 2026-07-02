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

WEIGHTS = {
    "stablecoins_usd": 0.18,
    "rwa_usd": 0.18,
    "tvl_sol": 0.13,
    "tvl_usd": 0.10,
    "dex_volume_usd": 0.10,
    "app_fees_usd": 0.09,
    "chain_fees_usd": 0.08,
    "active_addresses": 0.07,
    "sol_btc": 0.07,
}

ABSOLUTE_THRESHOLDS = {
    "stablecoins_usd": (5_000_000_000, 10_000_000_000),
    "rwa_usd": (500_000_000, 1_500_000_000),
    "tvl_usd": (2_000_000_000, 4_000_000_000),
    "dex_volume_usd": (500_000_000, 1_500_000_000),
    "app_fees_usd": (1_000_000, 4_000_000),
    "chain_fees_usd": (150_000, 500_000),
    "active_addresses": (500_000, 2_000_000),
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
        return 35
    if value >= high:
        return 80
    return 35 + (value - low) / (high - low) * 45


def metric_score(key: str, current: dict[str, Any], past: dict[str, Any] | None) -> tuple[float, float | None, str]:
    g = growth_pct(current, past, key)
    if g is not None:
        if g >= 20:
            return 90, g, "stark verbessert"
        if g >= 8:
            return 78, g, "verbessert"
        if g >= -5:
            return 58, g, "stabil"
        if g >= -15:
            return 42, g, "schwächer"
        return 25, g, "deutlich schwächer"
    abs_score = absolute_score(key, current.get(key))
    if abs_score is not None:
        return abs_score, None, "absolut bewertet"
    return 50, None, "neutral"


def compute_fundamental_score(current: dict[str, Any], past: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = []
    weighted = 0.0
    used = 0.0
    for key, weight in WEIGHTS.items():
        score, g, note = metric_score(key, current, past)
        if current.get(key) is None and g is None:
            continue
        rows.append({"key": key, "label": LABELS.get(key, key), "score": score, "growth_pct": g, "note": note, "weight": weight})
        weighted += score * weight
        used += weight
    final = weighted / used if used else 50.0
    if final >= 70:
        status = "intakt"
    elif final < 40:
        status = "geschwaecht"
    else:
        status = "neutral"
    return {"score": round(final, 2), "status": status, "details": rows, "growth_pct": {r["key"]: r["growth_pct"] for r in rows}}


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
    if status == "intakt":
        return f"Score {score:.0f}/100: Die Solana-These wirkt auf Basis der verfügbaren Fundamentaldaten intakt."
    if status == "geschwaecht":
        return f"Score {score:.0f}/100: Die Solana-These wirkt geschwächt. Prüfe die roten Kennzahlen im Detail."
    return f"Score {score:.0f}/100: Die Datenlage ist gemischt oder noch unvollständig."
