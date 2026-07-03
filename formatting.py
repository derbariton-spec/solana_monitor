from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import pandas as pd


def is_missing(value: Any) -> bool:
    try:
        return value is None or pd.isna(value)
    except Exception:
        return value is None


def safe_float(value: Any, fallback: Any = 0.0) -> float | None:
    """Convert a value to float without crashing on None or API strings.

    Important: some callers intentionally pass fallback=None to mean
    "missing value". The previous implementation tried float(None), which
    crashed the app when Binance returned an empty funding value.
    """
    try:
        if is_missing(value):
            return fallback if fallback is None else float(fallback)
        return float(value)
    except Exception:
        return fallback if fallback is None else float(fallback)


def fmt_number(value: Any, decimals: int = 2) -> str:
    if is_missing(value):
        return "n/a"
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_usd(value: Any) -> str:
    if is_missing(value):
        return "n/a"
    value = float(value)
    sign = "-" if value < 0 else ""
    value_abs = abs(value)
    if value_abs >= 1e9:
        return f"{sign}{value_abs / 1e9:,.2f} Mrd. $".replace(",", "X").replace(".", ",").replace("X", ".")
    if value_abs >= 1e6:
        return f"{sign}{value_abs / 1e6:,.2f} Mio. $".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{value_abs:,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_eur(value: Any) -> str:
    if is_missing(value):
        return "n/a"
    value = float(value)
    sign = "-" if value < 0 else ""
    value_abs = abs(value)
    if value_abs >= 1e9:
        return f"{sign}{value_abs / 1e9:,.2f} Mrd. €".replace(",", "X").replace(".", ",").replace("X", ".")
    if value_abs >= 1e6:
        return f"{sign}{value_abs / 1e6:,.2f} Mio. €".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{value_abs:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: Any, decimals: int = 2) -> str:
    if is_missing(value):
        return "n/a"
    return f"{float(value):+,.{decimals}f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_datetime_utc(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value)


def compact_label(value: Any) -> str:
    if is_missing(value):
        return "n/a"
    value = float(value)
    if abs(value) >= 1e9:
        return f"{value/1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{value/1e6:.2f}M"
    if abs(value) >= 1e3:
        return f"{value/1e3:.2f}K"
    return f"{value:.2f}"
