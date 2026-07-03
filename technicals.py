from __future__ import annotations

from typing import Any

import pandas as pd


def _last_float(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    value = series.dropna().iloc[-1] if not series.dropna().empty else None
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    close = pd.to_numeric(close, errors="coerce")
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return pd.DataFrame({"macd": macd, "signal": sig, "histogram": hist})


def detect_macd_cross(macd_df: pd.DataFrame) -> dict[str, Any]:
    if macd_df is None or len(macd_df.dropna()) < 2:
        return {"type": None, "label": "Zu wenig Daten", "days_ago": None}
    d = macd_df.dropna().copy()
    diff = d["macd"] - d["signal"]
    last_cross = None
    for i in range(1, len(diff)):
        prev, cur = diff.iloc[i - 1], diff.iloc[i]
        if prev <= 0 < cur:
            last_cross = (i, "bullish")
        elif prev >= 0 > cur:
            last_cross = (i, "bearish")
    if not last_cross:
        current = "bullish" if diff.iloc[-1] > 0 else "bearish" if diff.iloc[-1] < 0 else "neutral"
        return {"type": current, "label": f"Kein frisches Crossing · MACD aktuell {current}", "days_ago": None}
    idx, typ = last_cross
    days_ago = len(diff) - 1 - idx
    label = "Bullish MACD Cross" if typ == "bullish" else "Bearish MACD Cross"
    if days_ago == 0:
        label += " heute"
    elif days_ago == 1:
        label += " gestern"
    else:
        label += f" vor {days_ago} Tagen"
    return {"type": typ, "label": label, "days_ago": days_ago}


def detect_engulfing(candles: pd.DataFrame) -> dict[str, Any]:
    needed = {"open", "high", "low", "close"}
    if candles is None or candles.empty or not needed.issubset(candles.columns) or len(candles.dropna(subset=list(needed))) < 2:
        return {"type": None, "label": "Zu wenig Kerzendaten"}
    d = candles.dropna(subset=list(needed)).copy().sort_values("time") if "time" in candles.columns else candles.dropna(subset=list(needed)).copy()
    prev = d.iloc[-2]
    cur = d.iloc[-1]
    prev_open, prev_close = float(prev["open"]), float(prev["close"])
    cur_open, cur_close = float(cur["open"]), float(cur["close"])
    prev_bear = prev_close < prev_open
    prev_bull = prev_close > prev_open
    cur_bull = cur_close > cur_open
    cur_bear = cur_close < cur_open
    bullish = prev_bear and cur_bull and cur_open <= prev_close and cur_close >= prev_open
    bearish = prev_bull and cur_bear and cur_open >= prev_close and cur_close <= prev_open
    if bullish:
        return {"type": "bullish", "label": "Bullish Engulfing auf Tagesbasis"}
    if bearish:
        return {"type": "bearish", "label": "Bearish Engulfing auf Tagesbasis"}
    return {"type": "neutral", "label": "Kein Engulfing-Muster in der letzten Tageskerze"}


def interpret_rsi(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 30:
        return "überverkauft"
    if value < 45:
        return "schwach"
    if value <= 55:
        return "neutral"
    if value <= 70:
        return "bullisch"
    return "überkauft"


def technical_summary(candles: pd.DataFrame) -> dict[str, Any]:
    if candles is None or candles.empty or "close" not in candles.columns:
        return {"ok": False, "message": "Keine Kerzendaten verfügbar."}
    d = candles.copy()
    if "time" in d.columns:
        d = d.sort_values("time")
    close = pd.to_numeric(d["close"], errors="coerce")
    rsi_series = compute_rsi(close)
    macd_df = compute_macd(close)
    rsi = _last_float(rsi_series)
    macd_last = macd_df.dropna().iloc[-1].to_dict() if not macd_df.dropna().empty else {}
    return {
        "ok": True,
        "rsi_14": rsi,
        "rsi_label": interpret_rsi(rsi),
        "macd": float(macd_last.get("macd")) if macd_last else None,
        "macd_signal": float(macd_last.get("signal")) if macd_last else None,
        "macd_histogram": float(macd_last.get("histogram")) if macd_last else None,
        "macd_cross": detect_macd_cross(macd_df),
        "engulfing": detect_engulfing(d),
    }


def technical_score(summary: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 50.0
    rsi = summary.get("rsi_14")
    if rsi is not None:
        rsi = float(rsi)
        if 45 <= rsi <= 65:
            score += 12
            reasons.append("RSI im gesunden bullischen/neutralen Bereich")
        elif 30 <= rsi < 45:
            score -= 4
            reasons.append("RSI eher schwach")
        elif 65 < rsi <= 75:
            score += 4
            reasons.append("RSI stark, aber nah an Überhitzung")
        elif rsi > 75:
            score -= 8
            reasons.append("RSI deutlich überkauft")
        else:
            score += 4
            reasons.append("RSI stark überverkauft, antizyklisch interessant")
    cross = (summary.get("macd_cross") or {}).get("type")
    days_ago = (summary.get("macd_cross") or {}).get("days_ago")
    if cross == "bullish":
        score += 16 if days_ago is not None and days_ago <= 7 else 8
        reasons.append("MACD bullisch")
    elif cross == "bearish":
        score -= 16 if days_ago is not None and days_ago <= 7 else 8
        reasons.append("MACD bearish")
    engulf = (summary.get("engulfing") or {}).get("type")
    if engulf == "bullish":
        score += 8
        reasons.append("Bullish Engulfing erkannt")
    elif engulf == "bearish":
        score -= 8
        reasons.append("Bearish Engulfing erkannt")
    return max(0, min(100, score)), reasons
