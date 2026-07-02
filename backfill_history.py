from __future__ import annotations

import argparse
import datetime as dt
import time

import pandas as pd
from dotenv import load_dotenv

from data_sources import (
    fetch_coin_market_chart,
    fetch_historical_dex_volume,
    fetch_historical_fees,
    fetch_historical_stablecoins,
    fetch_historical_tvl,
)
from scoring import compute_fundamental_score, interpretation_text
from storage import upsert_row

load_dotenv()


def _value(mapping: dict[str, float], date_str: str):
    return mapping.get(date_str)


def main(days: int = 1825) -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    print(f"Backfill Solana history: {start} bis {today}")

    tvl = fetch_historical_tvl(); time.sleep(1)
    stable = fetch_historical_stablecoins(); time.sleep(1)
    dex = fetch_historical_dex_volume(); time.sleep(1)
    app_fees = fetch_historical_fees("dailyFees"); time.sleep(1)
    app_revenue = fetch_historical_fees("dailyRevenue"); time.sleep(1)
    sol_prices = fetch_coin_market_chart("solana", days + 5); time.sleep(1)
    btc_prices = fetch_coin_market_chart("bitcoin", days + 5); time.sleep(1)

    if sol_prices.empty:
        raise RuntimeError("Keine SOL-Preisdaten geladen.")
    df = sol_prices.merge(btc_prices, on="snapshot_date", how="outer")
    df = df.rename(columns={"solana_usd": "sol_usd", "bitcoin_usd": "btc_usd"})
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df[(df["snapshot_date"].dt.date >= start) & (df["snapshot_date"].dt.date <= today)].sort_values("snapshot_date")

    previous_rows: list[dict] = []
    for _, r in df.iterrows():
        date = r["snapshot_date"].date()
        date_str = date.isoformat()
        sol_usd = r.get("sol_usd")
        btc_usd = r.get("btc_usd")
        sol_btc = (sol_usd / btc_usd) if pd.notna(sol_usd) and pd.notna(btc_usd) and btc_usd else None
        tvl_usd = _value(tvl, date_str)
        stablecoins_usd = _value(stable, date_str)
        dex_volume_usd = _value(dex, date_str)
        app_fees_usd = _value(app_fees, date_str)
        app_revenue_usd = _value(app_revenue, date_str)
        tvl_sol = (tvl_usd / sol_usd) if tvl_usd and pd.notna(sol_usd) and sol_usd else None
        current = {
            "sol_usd": sol_usd if pd.notna(sol_usd) else None,
            "sol_btc": sol_btc,
            "btc_usd": btc_usd if pd.notna(btc_usd) else None,
            "btc_dominance": None,
            "tvl_usd": tvl_usd,
            "tvl_sol": tvl_sol,
            "stablecoins_usd": stablecoins_usd,
            "rwa_usd": None,
            "dex_volume_usd": dex_volume_usd,
            "app_fees_usd": app_fees_usd,
            "app_revenue_usd": app_revenue_usd,
            "fees_usd": app_fees_usd,
            "revenue_usd": app_revenue_usd,
            "chain_fees_usd": None,
            "chain_revenue_usd": None,
            "active_addresses": None,
            "transactions_24h": None,
        }
        past = None
        past_date = date - dt.timedelta(days=30)
        for old in reversed(previous_rows):
            if old["date"] <= past_date:
                past = old["data"]
                break
        result = compute_fundamental_score(current, past)
        upsert_row({"snapshot_date": date_str, **current, "fundamental_score": result["score"], "thesis_status": result["status"], "note": interpretation_text(result)})
        previous_rows.append({"date": date, "data": current})
        print(f"{date_str}: SOL={current['sol_usd']} Score={result['score']}")
    print("Backfill fertig.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1825, help="Anzahl der Tage für den Backfill")
    args = parser.parse_args()
    main(args.days)
