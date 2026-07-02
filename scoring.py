from __future__ import annotations

from typing import Any

import pandas as pd

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

# Stock metrics are compared point-in-time against roughly 30 days ago.
STOCK_KEYS = {
    "stablecoins_usd",
    "rwa_usd",
    "tvl_usd",
    "tvl_sol",
    "sol_btc",
}

# Flow metrics are volatile day by day. They should be compared as rolling sums:
# latest 30 days vs previous 30 days.
FLOW_30D_KEYS = {
    "dex_volume_usd",
    "app_fees_usd",
    "app_revenue_usd",
    "chain_fees_usd",
    "chain_revenue_usd",
}

# Active addresses are volatile, so use a moving average instead of one day.
AVG_KEYS = {"active_addresses"}

# V4.2 scoring: structural Solana thesis.
# Missing optional metrics are excluded instead of being punished.
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

# Thresholds for point-in-time values.
ABSOLUTE_THRESHOLDS = {
    "stablecoins_usd": (5_000_000_000, 12_000_000_000),
    "rwa_usd": (500_000_000, 1_500_000_000),
    "tvl_usd": (2_000_000_000, 5_000_000_000),
    "dex_volume_usd": (500_000_000, 2_000_000_000),
    "app_fees_usd": (1_000_000, 5_000_000),
    "app_revenue_usd": (250_000, 2_000_000),
    "chain_fees_usd": (1_000_000, 5_000_000),
    "chain_revenue_usd": (250_000, 2_000_000),
    "active_addresses": (500_000, 2_500_000),
}

# Thresholds for 30-day rolling sums. These are deliberately broad because
# DeFiLlama flow metrics can vary by endpoint and update cadence.
ROLLING_30D_THRESHOLDS = {
    "dex_volume_usd": (20_000_000_000, 60_000_000_000),
    "app_fees_usd": (50_000_000, 180_000_000),
    "app_revenue_usd": (8_000_000, 60_000_000),
    "chain_fees_usd": (50_000_000, 180_000_000),
    "chain_revenue_usd": (8_000_000, 60_000_000),
}


def _is_missing(value: Any) -> bool:
    try:
        return value is None or pd.isna(value)
    except Exception:
        return value is None


def _prepare_history(history_df: pd.DataFrame | None, key: str) -> pd.DataFrame | None:
    if history_df is None or history_df.empty or key not in history_df.columns or "snapshot_date" not in history_df.columns:
        return None
    df = history_df[["snapshot_date", key]].copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")
    df[key] = pd.to_numeric(df[key], errors="coerce")
    df = df.dropna(subset=["snapshot_date", key]).sort_values("snapshot_date")
    if df.empty:
        return None
    return df


def _score_between(value: float, low: float, high: float) -> float:
    if value <= low:
        return 40.0
    if value >= high:
        return 86.0
    return 40.0 + (value - low) / (high - low) * 46.0


def growth_pct(current: dict[str, Any], past: dict[str, Any] | None, key: str) -> float | None:
    if not past:
        return None
    cur = current.get(key)
    old = past.get(key)
    if _is_missing(cur) or _is_missing(old):
        return None
    old_f = safe_float(old, 0)
    if old_f == 0:
        return None
    return (safe_float(cur) - old_f) / old_f * 100


def rolling_sum_change(history_df: pd.DataFrame | None, key: str, window_days: int = 30, min_points: int = 10) -> dict[str, Any]:
    df = _prepare_history(history_df, key)
    if df is None:
        return {"change_pct": None, "basis_value": None, "points_current": 0, "points_previous": 0}

    latest_date = df["snapshot_date"].max().normalize()
    current_start = latest_date - pd.Timedelta(days=window_days - 1)
    previous_end = current_start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=window_days - 1)

    current = df[(df["snapshot_date"] >= current_start) & (df["snapshot_date"] <= latest_date)][key].dropna()
    previous = df[(df["snapshot_date"] >= previous_start) & (df["snapshot_date"] <= previous_end)][key].dropna()

    if len(current) < min_points or len(previous) < min_points:
        return {"change_pct": None, "basis_value": None if current.empty else float(current.sum()), "points_current": len(current), "points_previous": len(previous)}

    cur_sum = float(current.sum())
    prev_sum = float(previous.sum())
    if prev_sum == 0:
        change = None
    else:
        change = (cur_sum - prev_sum) / prev_sum * 100
    return {"change_pct": change, "basis_value": cur_sum, "points_current": len(current), "points_previous": len(previous)}


def moving_average_change(history_df: pd.DataFrame | None, key: str, current_days: int = 7, baseline_days: int = 30, min_current: int = 3, min_baseline: int = 10) -> dict[str, Any]:
    df = _prepare_history(history_df, key)
    if df is None:
        return {"change_pct": None, "basis_value": None, "points_current": 0, "points_previous": 0}

    latest_date = df["snapshot_date"].max().normalize()
    current_start = latest_date - pd.Timedelta(days=current_days - 1)
    previous_end = current_start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=baseline_days - 1)

    current = df[(df["snapshot_date"] >= current_start) & (df["snapshot_date"] <= latest_date)][key].dropna()
    previous = df[(df["snapshot_date"] >= previous_start) & (df["snapshot_date"] <= previous_end)][key].dropna()

    if len(current) < min_current or len(previous) < min_baseline:
        return {"change_pct": None, "basis_value": None if current.empty else float(current.mean()), "points_current": len(current), "points_previous": len(previous)}

    cur_avg = float(current.mean())
    prev_avg = float(previous.mean())
    if prev_avg == 0:
        change = None
    else:
        change = (cur_avg - prev_avg) / prev_avg * 100
    return {"change_pct": change, "basis_value": cur_avg, "points_current": len(current), "points_previous": len(previous)}


def absolute_score(key: str, value: Any, *, rolling_30d: bool = False) -> float | None:
    if _is_missing(value):
        return None
    thresholds = ROLLING_30D_THRESHOLDS if rolling_30d else ABSOLUTE_THRESHOLDS
    if key not in thresholds:
        return None
    low, high = thresholds[key]
    return _score_between(safe_float(value), low, high)


def growth_score(g: float | None) -> float | None:
    if g is None:
        return None
    if g >= 20:
        return 92.0
    if g >= 8:
        return 82.0
    if g >= 0:
        return 68.0
    if g >= -5:
        return 56.0
    if g >= -15:
        return 42.0
    return 25.0


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


def metric_score(
    key: str,
    current: dict[str, Any],
    past: dict[str, Any] | None,
    history_df: pd.DataFrame | None = None,
) -> tuple[float | None, float | None, str, str, float | None]:
    """Return score, trend pct, note, comparison label, basis value.

    For stock metrics, trend pct means point-in-time vs about 30 days ago.
    For flow metrics, trend pct means latest 30-day sum vs previous 30-day sum.
    For active addresses, trend pct means recent 7-day average vs prior 30-day average.
    """
    value = current.get(key)
    if _is_missing(value):
        return None, None, "nicht verfügbar", "n/a", None

    if key in FLOW_30D_KEYS:
        rolling = rolling_sum_change(history_df, key)
        trend = rolling["change_pct"]
        basis_value = rolling["basis_value"]
        trend_s = growth_score(trend)
        abs_s = absolute_score(key, basis_value, rolling_30d=True) if basis_value is not None else absolute_score(key, value)
        comparison = "30D-Summe vs vorige 30D" if trend is not None else "zu wenig Rolling-Historie"
        if trend_s is not None and abs_s is not None:
            score = 0.65 * abs_s + 0.35 * trend_s
            return score, trend, f"{growth_note(trend)} · 30D-Rolling bewertet", comparison, basis_value
        if abs_s is not None:
            return abs_s, trend, "30D-Summe absolut bewertet" if basis_value is not None else "Tageswert absolut bewertet", comparison, basis_value
        return 50.0, None, "neutral", comparison, basis_value

    if key in AVG_KEYS:
        avg = moving_average_change(history_df, key)
        trend = avg["change_pct"]
        basis_value = avg["basis_value"]
        trend_s = growth_score(trend)
        abs_s = absolute_score(key, basis_value if basis_value is not None else value)
        comparison = "7D-Ø vs vorige 30D" if trend is not None else "zu wenig Ø-Historie"
        if trend_s is not None and abs_s is not None:
            score = 0.70 * abs_s + 0.30 * trend_s
            return score, trend, f"{growth_note(trend)} · geglättet bewertet", comparison, basis_value
        if abs_s is not None:
            return abs_s, trend, "absolut bewertet", comparison, basis_value
        return 50.0, None, "neutral", comparison, basis_value

    # Stock metrics: current point-in-time value vs about 30 days ago.
    trend = growth_pct(current, past, key)
    trend_s = growth_score(trend)
    abs_s = absolute_score(key, value)
    comparison = "Bestandswert vs vor 30T" if trend is not None else "zu wenig Historie"

    if trend_s is not None and abs_s is not None:
        score = 0.60 * abs_s + 0.40 * trend_s
        return score, trend, f"{growth_note(trend)} · strukturell bewertet", comparison, None
    if abs_s is not None:
        return abs_s, trend, "absolut bewertet", comparison, None
    if trend_s is not None:
        return trend_s, trend, growth_note(trend), comparison, None
    return 50.0, None, "neutral", comparison, None


def compute_fundamental_score(
    current: dict[str, Any],
    past: dict[str, Any] | None = None,
    history_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    rows = []
    weighted = 0.0
    used = 0.0
    missing = []
    for key, weight in WEIGHTS.items():
        score, trend, note, comparison, basis_value = metric_score(key, current, past, history_df)
        if score is None:
            missing.append(key)
            continue
        rows.append({
            "key": key,
            "label": LABELS.get(key, key),
            "score": score,
            "growth_pct": trend,  # backward-compatible name used by the app
            "trend_pct": trend,
            "note": note,
            "comparison": comparison,
            "basis_value": basis_value,
            "weight": weight,
        })
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
    method = " Flows werden als 30D-Rolling-Summe bewertet; aktive Adressen geglättet."
    if status == "intakt":
        return f"Score {score:.0f}/100: Die Solana-These wirkt auf Basis der verfügbaren Fundamentaldaten intakt.{suffix}{method}"
    if status == "geschwaecht":
        return f"Score {score:.0f}/100: Die Solana-These wirkt geschwächt. Prüfe die roten Kennzahlen im Detail.{suffix}{method}"
    return f"Score {score:.0f}/100: Die Datenlage ist gemischt oder noch unvollständig.{suffix}{method}"
