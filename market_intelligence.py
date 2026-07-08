from __future__ import annotations

from typing import Any

import pandas as pd

from formatting import fmt_eur, fmt_number, fmt_pct, fmt_usd, safe_float
from technicals import technical_summary


def _clean_candles(candles: pd.DataFrame | None) -> pd.DataFrame:
    if candles is None or candles.empty:
        return pd.DataFrame()
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(candles.columns):
        return pd.DataFrame()
    df = candles.copy()
    if "time" in df.columns:
        df = df.sort_values("time")
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=list(needed))


def _cluster_levels(values: list[float], tolerance_pct: float = 1.2, limit: int = 5) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters:
            clusters.append([value])
            continue
        center = sum(clusters[-1]) / len(clusters[-1])
        if center and abs(value - center) / center * 100 <= tolerance_pct:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    levels = [sum(cluster) / len(cluster) for cluster in clusters]
    return levels[:limit]


def swing_levels(candles: pd.DataFrame | None, price: float | None, lookback: int = 96) -> dict[str, list[float]]:
    df = _clean_candles(candles).tail(lookback)
    px = safe_float(price, None)
    if df.empty or px is None:
        return {"support": [], "resistance": []}

    highs: list[float] = []
    lows: list[float] = []
    rows = df.reset_index(drop=True)
    for i in range(2, len(rows) - 2):
        high = float(rows.loc[i, "high"])
        low = float(rows.loc[i, "low"])
        if high >= max(float(rows.loc[i - 1, "high"]), float(rows.loc[i - 2, "high"]), float(rows.loc[i + 1, "high"]), float(rows.loc[i + 2, "high"])):
            highs.append(high)
        if low <= min(float(rows.loc[i - 1, "low"]), float(rows.loc[i - 2, "low"]), float(rows.loc[i + 1, "low"]), float(rows.loc[i + 2, "low"])):
            lows.append(low)

    resistance = [level for level in _cluster_levels(highs, limit=12) if level > px * 1.003]
    support = [level for level in _cluster_levels(lows, limit=12) if level < px * 0.997]
    resistance = sorted(resistance, key=lambda v: abs(v - px))[:3]
    support = sorted(support, key=lambda v: abs(v - px))[:3]
    return {"support": sorted(support, reverse=True), "resistance": sorted(resistance)}


def market_structure(candles: pd.DataFrame | None) -> dict[str, Any]:
    df = _clean_candles(candles).tail(80)
    tech = technical_summary(df)
    if df.empty or len(df) < 20:
        return {"label": "n/a", "detail": "Zu wenig Kerzendaten", "technical": tech}

    close = df["close"]
    ema_20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1] if len(close) >= 50 else close.rolling(30).mean().iloc[-1]
    last = float(close.iloc[-1])
    prev_low = float(df["low"].tail(12).iloc[:-1].min())
    prior_low = float(df["low"].tail(28).iloc[:-12].min()) if len(df) >= 28 else prev_low

    higher_low = prev_low >= prior_low * 0.985
    above_ema = last >= ema_20 >= ema_50
    rsi = safe_float(tech.get("rsi_14"), None)

    if above_ema and higher_low and rsi is not None and rsi < 70:
        label = "Accumulation"
        detail = "Higher Low im Aufbau, Preis bleibt über den gleitenden Durchschnitten."
    elif above_ema:
        label = "Uptrend"
        detail = "Preis handelt über den kurzfristigen Trendlinien."
    elif higher_low:
        label = "Retest"
        detail = "Struktur verteidigt die letzten Tiefs, aber Momentum ist noch nicht klar."
    else:
        label = "Distribution risk"
        detail = "Struktur verliert kurzfristige Tiefs oder handelt unter Trendlinien."

    return {
        "label": label,
        "detail": detail,
        "higher_low": higher_low,
        "above_ema": bool(above_ema),
        "ema_20": float(ema_20),
        "ema_50": float(ema_50),
        "technical": tech,
    }


def liquidity_bias(price: float | None, levels: dict[str, list[float]], signal_report: dict[str, Any] | None = None) -> dict[str, Any]:
    px = safe_float(price, None)
    resistance = levels.get("resistance") or []
    support = levels.get("support") or []
    up = resistance[:2]
    down = support[:2]

    score = safe_float((signal_report or {}).get("timing_score"), 50.0)
    if px and up and down:
        nearest_up = abs(up[0] - px) / px
        nearest_down = abs(px - down[0]) / px
        score += max(-12, min(12, (nearest_down - nearest_up) * 180))
    score = max(25.0, min(75.0, score))
    up_probability = round(score)
    down_probability = 100 - up_probability

    if up_probability >= 58:
        bias = "Upside liquidity favored"
    elif up_probability <= 42:
        bias = "Downside liquidity risk"
    else:
        bias = "Two-sided liquidity"

    return {
        "bias": bias,
        "upside_targets": up,
        "downside_targets": down,
        "up_probability": up_probability,
        "down_probability": down_probability,
    }


def macro_layer(signal_report: dict[str, Any] | None, live: dict[str, Any] | None, latest: dict[str, Any] | None) -> list[dict[str, str]]:
    signal_report = signal_report or {}
    live = live or {}
    latest = latest or {}
    fear = signal_report.get("fear_greed") or {}
    alt = signal_report.get("altcoin_season") or {}
    oi = signal_report.get("open_interest") or {}
    funding = signal_report.get("funding") or {}

    btc_24h = safe_float(live.get("btc_24h_change"), None)
    sol_btc = safe_float(latest.get("sol_btc"), None)
    funding_pct = safe_float(funding.get("funding_rate_pct"), None)
    oi_change = safe_float(oi.get("open_interest_30d_pct"), None)

    return [
        {
            "Layer": "Fear & Greed",
            "Status": str(fear.get("label") or "n/a"),
            "Lesart": "Sentiment-Risiko" if safe_float(fear.get("value"), 50) > 75 else "brauchbar",
        },
        {
            "Layer": "Altcoin/Crypto Liquidity",
            "Status": str(alt.get("label") or "n/a"),
            "Lesart": "Rückenwind" if safe_float(alt.get("value"), 50) >= 55 else "neutral/abwarten",
        },
        {
            "Layer": "BTC 24h",
            "Status": "n/a" if btc_24h is None else fmt_pct(btc_24h),
            "Lesart": "Makro stabil" if btc_24h is not None and btc_24h > -2 else "Risk-off beobachten",
        },
        {
            "Layer": "SOL/BTC",
            "Status": "n/a" if sol_btc is None else fmt_number(sol_btc, 6),
            "Lesart": "Relative Stärke vorhanden" if sol_btc is not None else "keine Daten",
        },
        {
            "Layer": "Funding / OI",
            "Status": "n/a" if funding_pct is None else f"{funding_pct:.4f}%",
            "Lesart": "Hebel steigt" if oi_change is not None and oi_change > 10 else "Hebel nicht auffällig",
        },
    ]


def position_impact_rows(portfolio: dict[str, Any] | None, live: dict[str, Any] | None, moves: tuple[int, ...] = (10, 25, 50)) -> list[dict[str, str]]:
    portfolio = portfolio or {}
    live = live or {}
    exposure_sol = safe_float(portfolio.get("sol_equivalent"), 0.0) + safe_float(portfolio.get("sol_balance"), 0.0)
    sol_usd = safe_float(live.get("sol_usd"), 0.0)
    sol_eur = safe_float(live.get("sol_eur"), 0.0)
    eur_per_usd = (sol_eur / sol_usd) if sol_usd and sol_eur else 0.0
    rows: list[dict[str, str]] = []
    for move in moves:
        usd = exposure_sol * move
        eur = usd * eur_per_usd if eur_per_usd else None
        rows.append({
            "SOL Move": f"+/- {move} $",
            "Portfolio USD": f"+/- {fmt_usd(usd)}",
            "Portfolio EUR": "+/- n/a" if eur is None else f"+/- {fmt_eur(eur)}",
        })
    return rows


def ai_interpretation(
    live: dict[str, Any] | None,
    structure: dict[str, Any],
    levels: dict[str, list[float]],
    liquidity: dict[str, Any],
    signal_report: dict[str, Any] | None,
) -> str:
    live = live or {}
    price = safe_float(live.get("sol_usd"), None)
    tech = structure.get("technical") or {}
    rsi = safe_float(tech.get("rsi_14"), None)
    timing = safe_float((signal_report or {}).get("timing_score"), None)
    support = levels.get("support") or []
    resistance = levels.get("resistance") or []
    parts = []
    if price is not None:
        parts.append(f"SOL handelt bei {fmt_usd(price)}.")
    parts.append(f"Die aktuelle Struktur wirkt wie {structure.get('label', 'n/a')}: {structure.get('detail', '')}")
    if rsi is not None:
        parts.append(f"RSI liegt bei {rsi:.1f}; das spricht eher für Reset/Trendfortsetzung als für blinde Euphorie." if 45 <= rsi <= 68 else f"RSI liegt bei {rsi:.1f} und sollte als Risiko-/Timingfilter gelesen werden.")
    if resistance:
        parts.append(f"Nächste Upside-Liquidität liegt technisch um {', '.join(fmt_usd(x) for x in resistance[:2])}.")
    if support:
        parts.append(f"Wichtige Retest-Zone liegt um {', '.join(fmt_usd(x) for x in support[:2])}.")
    if timing is not None:
        parts.append(f"Timing Score {timing:.0f}/100; Bias: {liquidity.get('bias')} mit {liquidity.get('up_probability')}% Upside-Sweep gegen {liquidity.get('down_probability')}% Breakdown-Risiko.")
    return " ".join(parts)


def build_market_intelligence(
    candles: pd.DataFrame | None,
    live: dict[str, Any] | None,
    portfolio: dict[str, Any] | None,
    latest: dict[str, Any] | None = None,
    signal_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price = safe_float((live or {}).get("sol_usd"), None)
    structure = market_structure(candles)
    levels = swing_levels(candles, price)
    liquidity = liquidity_bias(price, levels, signal_report)
    return {
        "structure": structure,
        "levels": levels,
        "liquidity": liquidity,
        "macro": macro_layer(signal_report, live, latest),
        "position_rows": position_impact_rows(portfolio, live),
        "interpretation": ai_interpretation(live, structure, levels, liquidity, signal_report),
    }
