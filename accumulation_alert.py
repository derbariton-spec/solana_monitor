from __future__ import annotations

from typing import Any

import pandas as pd

from formatting import safe_float


def _clean_candles(candles: pd.DataFrame | None) -> pd.DataFrame:
    if candles is None or candles.empty:
        return pd.DataFrame()
    needed = {"time", "high", "low", "close"}
    if not needed.issubset(candles.columns):
        return pd.DataFrame()
    d = candles.copy()
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    for col in ("high", "low", "close"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    return d.dropna(subset=["time", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def _pivot_lows(d: pd.DataFrame, window: int) -> list[int]:
    lows: list[int] = []
    for idx in range(window, len(d) - window):
        value = float(d.loc[idx, "low"])
        area = d.loc[idx - window: idx + window, "low"]
        if value <= float(area.min()):
            lows.append(idx)
    return lows


def _pivot_highs(d: pd.DataFrame, window: int) -> list[int]:
    highs: list[int] = []
    for idx in range(window, len(d) - window):
        value = float(d.loc[idx, "high"])
        area = d.loc[idx - window: idx + window, "high"]
        if value >= float(area.max()):
            highs.append(idx)
    return highs


def _find_last_up_swing(d: pd.DataFrame, pivot_window: int, min_move_pct: float) -> tuple[int, int] | None:
    lows = _pivot_lows(d, pivot_window)
    highs = _pivot_highs(d, pivot_window)
    if not lows or not highs:
        return None

    for high_idx in reversed(highs):
        prior_lows = [idx for idx in lows if idx < high_idx]
        for low_idx in reversed(prior_lows):
            low = float(d.loc[low_idx, "low"])
            high = float(d.loc[high_idx, "high"])
            if low > 0 and (high - low) / low * 100 >= min_move_pct:
                return low_idx, high_idx
    return None


def build_accumulation_alert(
    candles: pd.DataFrame | None,
    live_price: Any = None,
    pivot_window: int = 3,
    min_move_pct: float = 15.0,
    tolerance_pct: float = 2.0,
) -> dict[str, Any]:
    d = _clean_candles(candles)
    if len(d) < max(30, pivot_window * 4):
        return {"ok": False, "status": "n/a", "label": "Zu wenig Kerzendaten", "message": "Für den Nachkauf-Alert fehlen ausreichend Tageskerzen."}

    swing = _find_last_up_swing(d, pivot_window=pivot_window, min_move_pct=min_move_pct)
    if swing is None:
        return {"ok": False, "status": "neutral", "label": "Kein klarer Aufwärtsswing", "message": "Es wurde keine ausreichend starke letzte Aufwärtsbewegung erkannt."}

    low_idx, high_idx = swing
    low = float(d.loc[low_idx, "low"])
    high = float(d.loc[high_idx, "high"])
    move = high - low
    fib_50 = high - move * 0.5
    fib_618 = high - move * 0.618
    fib_786 = high - move * 0.786
    current = safe_float(live_price, None) or float(d["close"].iloc[-1])
    distance_pct = (current - fib_618) / fib_618 * 100 if fib_618 else None
    touched_zone = current <= fib_618 * (1 + tolerance_pct / 100) and current >= fib_786 * 0.98

    if current < fib_786:
        status = "risk"
        label = "unter 78,6% Retracement"
        message = "Der Kurs liegt tiefer als die normale 61er-Nachkaufzone. Erst Stabilisierung abwarten."
    elif touched_zone:
        status = "active"
        label = "Nachkauf-Zone aktiv"
        message = "Der Kurs läuft das 61,8%-Retracement der letzten Aufwärtsbewegung an."
    elif current > fib_618:
        status = "watch"
        label = "Nachkauf-Zone beobachten"
        message = "Das 61,8%-Retracement ist noch nicht erreicht."
    else:
        status = "neutral"
        label = "Retracement angelaufen"
        message = "Der Kurs liegt in der tieferen Retracement-Zone; Momentum und News prüfen."

    return {
        "ok": True,
        "status": status,
        "label": label,
        "message": message,
        "current_price": round(current, 4),
        "swing_low": round(low, 4),
        "swing_high": round(high, 4),
        "fib_50": round(fib_50, 4),
        "fib_618": round(fib_618, 4),
        "fib_786": round(fib_786, 4),
        "distance_pct": None if distance_pct is None else round(distance_pct, 2),
        "tolerance_pct": tolerance_pct,
        "swing_low_date": d.loc[low_idx, "time"].date().isoformat(),
        "swing_high_date": d.loc[high_idx, "time"].date().isoformat(),
    }


def accumulation_alert_rows(alert: dict[str, Any]) -> list[dict[str, str]]:
    if not alert.get("ok"):
        return [{"Punkt": "Status", "Wert": str(alert.get("label", "n/a")), "Hinweis": str(alert.get("message", ""))}]
    return [
        {"Punkt": "Aktueller SOL/USD", "Wert": f"${alert['current_price']:.2f}", "Hinweis": str(alert.get("label", ""))},
        {"Punkt": "Swing Low", "Wert": f"${alert['swing_low']:.2f}", "Hinweis": str(alert.get("swing_low_date", ""))},
        {"Punkt": "Swing High", "Wert": f"${alert['swing_high']:.2f}", "Hinweis": str(alert.get("swing_high_date", ""))},
        {"Punkt": "50,0% Retracement", "Wert": f"${alert['fib_50']:.2f}", "Hinweis": "erste Pullback-Zone"},
        {"Punkt": "61,8% Retracement", "Wert": f"${alert['fib_618']:.2f}", "Hinweis": "Investor-Nachkaufzone"},
        {"Punkt": "78,6% Retracement", "Wert": f"${alert['fib_786']:.2f}", "Hinweis": "unterhalb davon Risiko prüfen"},
        {"Punkt": "Abstand zum 61er", "Wert": f"{alert['distance_pct']:+.2f}%", "Hinweis": "positiv = Kurs liegt noch darüber"},
    ]
