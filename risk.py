from __future__ import annotations

from typing import Any

from formatting import fmt_pct, safe_float


def accumulation_signal(sol_usd: float | None, low_zone: float = 150.0, high_zone: float = 220.0) -> dict[str, str]:
    price = safe_float(sol_usd, 0.0)
    if price <= 0:
        return {"Status": "⚪", "Signal": "keine Kursdaten", "Begründung": "SOL/USD fehlt"}
    if price < low_zone:
        return {"Status": "🟢", "Signal": "Akkumulationszone", "Begründung": f"SOL liegt unter {low_zone:.0f} USD"}
    if price > high_zone:
        return {"Status": "🔴", "Signal": "überhitzt / vorsichtig", "Begründung": f"SOL liegt über {high_zone:.0f} USD"}
    return {"Status": "🟡", "Signal": "neutral", "Begründung": f"SOL liegt zwischen {low_zone:.0f} und {high_zone:.0f} USD"}


def hedge_signal(result: dict[str, Any], live: dict[str, Any]) -> dict[str, str]:
    score = safe_float(result.get("score"), 50.0)
    sol_24h = live.get("sol_24h_change")
    weak_metrics = [d for d in result.get("details", []) if safe_float(d.get("score"), 50) < 55]
    reasons: list[str] = []
    risk_points = 0
    if score < 55:
        risk_points += 1
        reasons.append(f"Score nur {score:.0f}/100")
    if sol_24h is not None and safe_float(sol_24h) < -5:
        risk_points += 1
        reasons.append(f"SOL 24h {fmt_pct(sol_24h)}")
    if len(weak_metrics) >= 3:
        risk_points += 1
        reasons.append(f"{len(weak_metrics)} schwache Kennzahlen")
    if risk_points >= 2:
        return {"Status": "🔴", "Signal": "Hedge prüfen", "Begründung": "; ".join(reasons)}
    if risk_points == 1:
        return {"Status": "🟡", "Signal": "beobachten", "Begründung": "; ".join(reasons)}
    return {"Status": "🟢", "Signal": "kein Hedge-Signal", "Begründung": "Score/Markt aktuell ohne starkes Warnsignal"}


def build_risk_rows(result: dict[str, Any], live: dict[str, Any], low_zone: float = 150.0, high_zone: float = 220.0) -> list[dict[str, str]]:
    acc = accumulation_signal(live.get("sol_usd"), low_zone, high_zone)
    hedge = hedge_signal(result, live)
    rows = [
        {"Status": acc["Status"], "Bereich": "Nachkauf-Ampel", "Signal": acc["Signal"], "Begründung": acc["Begründung"]},
        {"Status": hedge["Status"], "Bereich": "Hedge-Ampel", "Signal": hedge["Signal"], "Begründung": hedge["Begründung"]},
    ]
    return rows
