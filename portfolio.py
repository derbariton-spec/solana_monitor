from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from typing import Any

from formatting import safe_float


@dataclass
class PositionSettings:
    wallet_address: str = ""
    manual_jitosol_amount: float = 0.0
    manual_sol_equivalent: float = 0.0
    avg_entry_jitosol_usd: float = 0.0
    historical_sol_entry_usd: float = 0.0
    bought_sol_basis: float = 0.0
    staking_start_date: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PositionSettings":
        data = data or {}
        return cls(
            wallet_address=str(data.get("wallet_address") or ""),
            manual_jitosol_amount=safe_float(data.get("manual_jitosol_amount"), safe_float(data.get("jitosol_amount"), 0.0)),
            manual_sol_equivalent=safe_float(data.get("manual_sol_equivalent"), safe_float(data.get("sol_equivalent"), 0.0)),
            avg_entry_jitosol_usd=safe_float(data.get("avg_entry_jitosol_usd"), 0.0),
            historical_sol_entry_usd=safe_float(data.get("historical_sol_entry_usd"), 0.0),
            bought_sol_basis=safe_float(data.get("bought_sol_basis"), 0.0),
            staking_start_date=str(data.get("staking_start_date") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_portfolio(position: PositionSettings, wallet_summary: dict[str, Any] | None, live: dict[str, Any]) -> dict[str, Any]:
    sol_usd = safe_float(live.get("sol_usd"), 0.0)
    sol_eur = safe_float(live.get("sol_eur"), 0.0)
    jito_usd = safe_float(live.get("jitosol_usd"), 0.0)
    jito_eur = safe_float(live.get("jitosol_eur"), 0.0)
    ratio = (jito_usd / sol_usd) if sol_usd and jito_usd else 0.0

    wallet_summary = wallet_summary or {}
    wallet_jito = safe_float(wallet_summary.get("jitosol_balance"), 0.0)
    wallet_sol = safe_float(wallet_summary.get("sol_balance"), 0.0)
    wallet_usdc = safe_float(wallet_summary.get("usdc_balance"), 0.0)

    jitosol_amount = wallet_jito if wallet_summary.get("ok") and wallet_jito else position.manual_jitosol_amount
    sol_balance = wallet_sol if wallet_summary.get("ok") else 0.0
    usdc_balance = wallet_usdc if wallet_summary.get("ok") else 0.0
    sol_equivalent = jitosol_amount * ratio if ratio else position.manual_sol_equivalent

    jito_value_usd = jitosol_amount * jito_usd if jito_usd else sol_equivalent * sol_usd
    jito_value_eur = jitosol_amount * jito_eur if jito_eur else sol_equivalent * sol_eur
    sol_value_usd = sol_balance * sol_usd
    sol_value_eur = sol_balance * sol_eur
    total_usd = jito_value_usd + sol_value_usd + usdc_balance
    total_eur = jito_value_eur + sol_value_eur + (usdc_balance * (sol_eur / sol_usd) if sol_usd and sol_eur else 0.0)

    cost_basis_usd = jitosol_amount * position.avg_entry_jitosol_usd if position.avg_entry_jitosol_usd else 0.0
    pnl_usd = jito_value_usd - cost_basis_usd if cost_basis_usd else 0.0
    pnl_pct = (jito_value_usd / cost_basis_usd - 1) * 100 if cost_basis_usd else 0.0

    staking_rewards_sol = None
    if position.bought_sol_basis:
        staking_rewards_sol = sol_equivalent - position.bought_sol_basis
    rewards_usd = staking_rewards_sol * sol_usd if staking_rewards_sol is not None else None
    rewards_eur = staking_rewards_sol * sol_eur if staking_rewards_sol is not None else None

    staking_apy = None
    if staking_rewards_sol is not None and position.bought_sol_basis and position.staking_start_date:
        try:
            start = dt.date.fromisoformat(position.staking_start_date)
            days = max((dt.date.today() - start).days, 1)
            total_return = staking_rewards_sol / position.bought_sol_basis
            staking_apy = ((1 + total_return) ** (365 / days) - 1) * 100
        except Exception:
            staking_apy = None

    return {
        "jitosol_amount": jitosol_amount,
        "sol_balance": sol_balance,
        "usdc_balance": usdc_balance,
        "jitosol_sol_ratio": ratio,
        "sol_equivalent": sol_equivalent,
        "jitosol_value_usd": jito_value_usd,
        "jitosol_value_eur": jito_value_eur,
        "sol_value_usd": sol_value_usd,
        "sol_value_eur": sol_value_eur,
        "total_usd": total_usd,
        "total_eur": total_eur,
        "cost_basis_usd": cost_basis_usd,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "staking_rewards_sol": staking_rewards_sol,
        "staking_rewards_usd": rewards_usd,
        "staking_rewards_eur": rewards_eur,
        "staking_apy": staking_apy,
    }
