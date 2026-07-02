"""Taeglicher Datensammler fuer den Solana Fundamental Monitor 2.1.

Laeuft lokal oder per GitHub Actions:
    python3 fetch_data.py

Speicherlogik:
- Wenn SUPABASE_URL + SUPABASE_SERVICE_KEY gesetzt sind: Supabase.
- Sonst: lokale CSV unter data/solana_fundamentals.csv.
"""

from __future__ import annotations

import datetime as dt
import sys

import pandas as pd
from dotenv import load_dotenv

from data_sources import (
    fetch_active_addresses,
    fetch_app_fees_usd,
    fetch_app_revenue_usd,
    fetch_btc_dominance,
    fetch_chain_fees_usd,
    fetch_chain_revenue_usd,
    fetch_dex_volume_usd,
    fetch_price,
    fetch_rwa_usd,
    fetch_stablecoins_usd,
    fetch_tvl_usd,
)
from score import compute_fundamental_score, interpretation_text
from storage import load_history, upsert_row

load_dotenv()


def _clean(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value)


def row_as_dict(row) -> dict | None:
    if row is None:
        return None
    return {key: _clean(row.get(key)) for key in row.index}


def main():
    today = dt.date.today()
    print(f"[{today}] Sammle Solana-Daten...")

    sol_usd, sol_btc, btc_usd = fetch_price()
    tvl_usd = fetch_tvl_usd()
    stablecoins_usd = fetch_stablecoins_usd()
    rwa_usd = fetch_rwa_usd()
    dex_volume_usd = fetch_dex_volume_usd()

    # DeFiLlama trennt App Fees/App Revenue von Chain Fees/Chain Revenue.
    app_fees_usd = fetch_app_fees_usd()
    app_revenue_usd = fetch_app_revenue_usd()
    chain_fees_usd = fetch_chain_fees_usd()
    chain_revenue_usd = fetch_chain_revenue_usd()

    btc_dominance = fetch_btc_dominance()
    active_addresses = fetch_active_addresses()
    tvl_sol = (tvl_usd / sol_usd) if tvl_usd and sol_usd else None

    current = {
        "sol_usd": sol_usd,
        "sol_btc": sol_btc,
        "btc_usd": btc_usd,
        "btc_dominance": btc_dominance,
        "tvl_usd": tvl_usd,
        "tvl_sol": tvl_sol,
        "stablecoins_usd": stablecoins_usd,
        "rwa_usd": rwa_usd,
        "dex_volume_usd": dex_volume_usd,

        # Rueckwaertskompatibel fuer App/Score:
        "fees_usd": app_fees_usd,
        "revenue_usd": app_revenue_usd,

        # Neue explizite Felder:
        "app_fees_usd": app_fees_usd,
        "app_revenue_usd": app_revenue_usd,
        "chain_fees_usd": chain_fees_usd,
        "chain_revenue_usd": chain_revenue_usd,

        "active_addresses": active_addresses,
    }

    df = load_history(days=370)
    target = pd.Timestamp(today) - pd.Timedelta(days=30)
    past = None
    if not df.empty:
        candidates = df[df["snapshot_date"] <= target]
        if not candidates.empty:
            past = row_as_dict(candidates.iloc[-1])

    result = compute_fundamental_score(current, past)

    row = {
        "snapshot_date": today.isoformat(),
        **current,
        "fundamental_score": result["score"],
        "thesis_status": result["status"],
        "note": result.get("note"),
    }
    upsert_row(row)

    print(f"[{today}] Gespeichert. Score: {result['score']}/100 ({result['status']})")
    print("Werte:")
    for key, value in current.items():
        print(f"  {key}: {value}")
    print(interpretation_text(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
