from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Any

import requests

from formatting import safe_float

COINGECKO_RANGE_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
REQUEST_TIMEOUT = 12
HEADERS = {"User-Agent": "solana-monitor/5.3"}


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


def _parse_iso_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except Exception:
        return None


@lru_cache(maxsize=128)
def _fetch_usd_price_near_date(coin_id: str, date_str: str) -> float | None:
    """Return an approximate USD price near a UTC date using CoinGecko range data.

    We intentionally use a small 3-day window and take the point closest to noon UTC
    of the requested date. This is good enough for estimating the JitoSOL/SOL ratio
    at a staking start date without needing a paid API.
    """
    target_date = _parse_iso_date(date_str)
    if target_date is None:
        return None

    start_dt = dt.datetime.combine(target_date - dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    end_dt = dt.datetime.combine(target_date + dt.timedelta(days=2), dt.time.min, tzinfo=dt.timezone.utc)
    target_ts_ms = int(
        dt.datetime.combine(target_date, dt.time(hour=12), tzinfo=dt.timezone.utc).timestamp() * 1000
    )

    try:
        url = COINGECKO_RANGE_URL.format(coin_id=coin_id)
        response = requests.get(
            url,
            params={"vs_currency": "usd", "from": int(start_dt.timestamp()), "to": int(end_dt.timestamp())},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        prices = response.json().get("prices") or []
        if not prices:
            return None
        closest = min(prices, key=lambda row: abs(int(row[0]) - target_ts_ms))
        return safe_float(closest[1], None)
    except Exception:
        return None


@lru_cache(maxsize=64)
def fetch_jitosol_sol_ratio_at_date(date_str: str) -> float | None:
    """Estimate historical JitoSOL/SOL ratio for a date.

    JitoSOL staking rewards are reflected by the token's exchange rate versus SOL.
    Therefore rewards since a start date must compare today's JitoSOL/SOL ratio with
    the ratio on that start date — not with 1.0.
    """
    jito_usd = _fetch_usd_price_near_date("jito-staked-sol", date_str)
    sol_usd = _fetch_usd_price_near_date("solana", date_str)
    if not jito_usd or not sol_usd:
        return None
    return jito_usd / sol_usd


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

    # Correct reward logic:
    # JitoSOL does NOT start at 1.0 SOL for a late buyer. Its exchange rate was already
    # above 1.0 on 2026-03-26 etc. So rewards since a start date are calculated against
    # the historical JitoSOL/SOL ratio on that date, not against 1.0 and not against an
    # arbitrary old default such as 200 SOL.
    ratio_at_start = None
    historical_basis_sol = None
    start_date = _parse_iso_date(position.staking_start_date)
    if start_date and jitosol_amount:
        ratio_at_start = fetch_jitosol_sol_ratio_at_date(start_date.isoformat())
        if ratio_at_start:
            historical_basis_sol = jitosol_amount * ratio_at_start

    manual_basis_sol = position.bought_sol_basis if position.bought_sol_basis and position.bought_sol_basis > 0 else None

    reward_basis_sol = None
    reward_basis_source = None
    manual_basis_difference_sol = None
    reward_warning = None

    if historical_basis_sol is not None:
        reward_basis_sol = historical_basis_sol
        reward_basis_source = f"historischer JitoSOL/SOL-Kurs am {start_date.isoformat()}"
        if manual_basis_sol is not None:
            manual_basis_difference_sol = manual_basis_sol - historical_basis_sol
            if abs(manual_basis_difference_sol) > max(2.0, sol_equivalent * 0.02):
                reward_warning = (
                    "Die manuelle Bought-SOL-Basis weicht deutlich von der historischen "
                    "JitoSOL/SOL-Schätzung ab. Für den angezeigten JitoSOL-Zuwachs wird "
                    "deshalb der historische Startkurs verwendet."
                )
    elif manual_basis_sol is not None:
        reward_basis_sol = manual_basis_sol
        reward_basis_source = "manuelle Bought-SOL-Basis"

    staking_rewards_sol = sol_equivalent - reward_basis_sol if reward_basis_sol is not None else None
    rewards_usd = staking_rewards_sol * sol_usd if staking_rewards_sol is not None else None
    rewards_eur = staking_rewards_sol * sol_eur if staking_rewards_sol is not None else None

    staking_apy = None
    if staking_rewards_sol is not None and reward_basis_sol and start_date:
        try:
            days = max((dt.date.today() - start_date).days, 1)
            total_return = staking_rewards_sol / reward_basis_sol
            if total_return > -0.95:
                staking_apy = ((1 + total_return) ** (365 / days) - 1) * 100
        except Exception:
            staking_apy = None

    return {
        "jitosol_amount": jitosol_amount,
        "sol_balance": sol_balance,
        "usdc_balance": usdc_balance,
        "jitosol_sol_ratio": ratio,
        "jitosol_sol_ratio_at_start": ratio_at_start,
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
        "staking_basis_sol": reward_basis_sol,
        "staking_basis_source": reward_basis_source,
        "manual_basis_difference_sol": manual_basis_difference_sol,
        "staking_reward_warning": reward_warning,
        "staking_rewards_sol": staking_rewards_sol,
        "staking_rewards_usd": rewards_usd,
        "staking_rewards_eur": rewards_eur,
        "staking_apy": staking_apy,
    }
