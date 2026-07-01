"""Fundamental Score fuer den Solana Fundamental Monitor 2.0.

Die Idee: Nicht der Tageskurs entscheidet, sondern ob die These staerker wird.
Jede Kennzahl wird gegen einen historischen Vergleichspunkt gemessen, standardmaessig
30 Tage. 0% Wachstum = 50 Punkte, starkes Wachstum geht Richtung 100, Rueckgang
Richtung 0. Fehlende Daten werden automatisch ignoriert.
"""

from __future__ import annotations

from config import GREEN_GROWTH, RED_GROWTH, WEIGHTS

LABELS = {
    "rwa_usd": "RWA",
    "stablecoins_usd": "Stablecoins",
    "tvl_usd": "TVL USD",
    "tvl_sol": "TVL in SOL",
    "sol_btc": "SOL/BTC",
    "dex_volume_usd": "DEX-Volumen",
    "fees_usd": "Fees",
    "revenue_usd": "Revenue",
    "active_addresses": "Active Addresses",
}


def growth_pct(current: float | None, past: float | None) -> float | None:
    if current is None or past is None or past == 0:
        return None
    try:
        return (float(current) - float(past)) / float(past) * 100.0
    except Exception:
        return None


def normalize(growth: float | None) -> float | None:
    if growth is None:
        return None
    # Etwas konservativer als v1: +50% / 30T = 100 Punkte, -50% = 0 Punkte.
    return max(0.0, min(100.0, 50.0 + growth))


def compute_fundamental_score(current: dict, past: dict | None) -> dict:
    past = past or {}
    growths = {key: growth_pct(current.get(key), past.get(key)) for key in WEIGHTS}
    components = {key: normalize(value) for key, value in growths.items()}
    available = {key: value for key, value in components.items() if value is not None}

    if not available:
        return {
            "score": 50.0,
            "status": "neutral",
            "components": components,
            "growth_pct": growths,
            "note": "Noch keine Vergleichshistorie vorhanden. Score neutral bei 50.",
        }

    total_weight = sum(WEIGHTS[key] for key in available)
    score = sum(available[key] * WEIGHTS[key] for key in available) / total_weight

    if score >= 68:
        status = "intakt"
    elif score >= 45:
        status = "neutral"
    else:
        status = "geschwaecht"

    return {
        "score": round(score, 1),
        "status": status,
        "components": components,
        "growth_pct": growths,
        "note": None,
    }


def traffic_light(growth: float | None) -> str:
    if growth is None:
        return "⚪"
    if growth >= GREEN_GROWTH:
        return "🟢"
    if growth <= RED_GROWTH:
        return "🔴"
    return "🟡"


def interpretation_text(result: dict) -> str:
    growths = result.get("growth_pct", {})
    items = []
    for key in WEIGHTS:
        g = growths.get(key)
        if g is None:
            continue
        label = LABELS.get(key, key)
        items.append(f"{traffic_light(g)} {label} {g:+.1f}%")

    status = result.get("status")
    if status == "intakt":
        verdict = "These: intakt – Wachstum ueberwiegt."
    elif status == "geschwaecht":
        verdict = "These: geschwaecht – mehrere Kernkennzahlen ruecklaeufig."
    else:
        verdict = "These: neutral/gemischt – weiter beobachten."

    return (" · ".join(items) + "\n\n" if items else "") + verdict
