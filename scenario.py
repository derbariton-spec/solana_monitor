from __future__ import annotations

from typing import Any

from formatting import safe_float

DEFAULT_TARGETS = [100, 130, 150, 200, 250, 500, 950]


def build_price_scenarios(portfolio: dict[str, Any], live: dict[str, Any], targets: list[float] | None = None, apy_pct: float = 6.5) -> list[dict[str, Any]]:
    targets = targets or DEFAULT_TARGETS
    sol_now = safe_float(live.get("sol_usd"), 0.0)
    eur_per_usd = safe_float(live.get("sol_eur"), 0.0) / sol_now if sol_now else 0.0
    sol_equiv = safe_float(portfolio.get("sol_equivalent"), 0.0)
    sol_balance = safe_float(portfolio.get("sol_balance"), 0.0)
    usdc = safe_float(portfolio.get("usdc_balance"), 0.0)
    total_sol_exposure = sol_equiv + sol_balance
    rows: list[dict[str, Any]] = []
    for target in targets:
        total_usd = total_sol_exposure * float(target) + usdc
        total_eur = total_usd * eur_per_usd if eur_per_usd else None
        one_year_rewards_sol = sol_equiv * apy_pct / 100 if sol_equiv else 0.0
        rows.append({
            "SOL Ziel USD": float(target),
            "Portfolio USD": total_usd,
            "Portfolio EUR": total_eur,
            "JitoSOL Rewards/Jahr SOL": one_year_rewards_sol,
            "Rewards/Jahr USD": one_year_rewards_sol * float(target),
            "Abstand zu heute": None if not sol_now else (float(target) / sol_now - 1) * 100,
        })
    return rows
