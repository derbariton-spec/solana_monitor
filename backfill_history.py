"""Historischer Backfill fuer den Solana Fundamental Monitor 3.0.

Zweck:
- Fuellt deine Datenbasis rueckwirkend mit historischen Zeitreihen.
- Danach sind 30/90/365-Tage-Vergleiche und Charts sofort sinnvoller.

Ausfuehrung lokal:
    python3 backfill_history.py --days 365
    python3 backfill_history.py --days 1825

Ausfuehrung per GitHub Actions:
- Workflow `Backfill Solana History` manuell starten.

Speicherung:
- Nutzt dieselbe `upsert_row`-Logik wie `fetch_data.py`.
- Wenn Supabase-Service-Secret konfiguriert ist: Supabase.
- Sonst: lokale CSV unter data/solana_fundamentals.csv.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from score import compute_fundamental_score, interpretation_text
from storage import load_history, upsert_row

load_dotenv()

TIMEOUT = 35
HEADERS = {"User-Agent": "solana-fundamental-monitor-backfill/3.0"}


def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.5 + attempt)
    raise RuntimeError(f"API request failed: {url} | {last_error}")


def ts_to_date(ts: int | float) -> str:
    return dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc).date().isoformat()


def ms_to_date(ms: int | float) -> str:
    return dt.datetime.fromtimestamp(float(ms) / 1000, tz=dt.timezone.utc).date().isoformat()


def as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def fetch_defillama_tvl() -> dict[str, float]:
    data = get_json("https://api.llama.fi/v2/historicalChainTvl/Solana")
    out: dict[str, float] = {}
    for row in data or []:
        value = as_float(row.get("tvl"))
        if value is not None and row.get("date") is not None:
            out[ts_to_date(row["date"])] = value
    return out


def fetch_stablecoins() -> dict[str, float]:
    data = get_json("https://stablecoins.llama.fi/stablecoincharts/Solana")
    out: dict[str, float] = {}
    for row in data or []:
        if row.get("date") is None:
            continue
        total = row.get("totalCirculatingUSD")
        value: float | None = None
        if isinstance(total, dict):
            vals = [as_float(v) for v in total.values()]
            value = sum(v for v in vals if v is not None)
        else:
            value = as_float(total)
        if value is not None:
            out[ts_to_date(row["date"])] = value
    return out


def fetch_llama_overview_chart(url: str, data_type: str) -> dict[str, float]:
    data = get_json(url, {"excludeTotalDataChartBreakdown": "true", "dataType": data_type})
    chart = data.get("totalDataChart") or []
    out: dict[str, float] = {}
    for row in chart:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        value = as_float(row[1])
        if value is not None:
            out[ts_to_date(row[0])] = value
    return out


def fetch_dex_volume() -> dict[str, float]:
    return fetch_llama_overview_chart("https://api.llama.fi/overview/dexs/Solana", "dailyVolume")


def fetch_app_fees() -> dict[str, float]:
    return fetch_llama_overview_chart("https://api.llama.fi/overview/fees/Solana", "dailyFees")


def fetch_app_revenue() -> dict[str, float]:
    return fetch_llama_overview_chart("https://api.llama.fi/overview/fees/Solana", "dailyRevenue")


def fetch_coin_market_chart(coin_id: str, days: int) -> pd.DataFrame:
    data = get_json(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        {"vs_currency": "usd", "days": days, "interval": "daily"},
    )
    rows: list[dict[str, Any]] = []
    for item in data.get("prices", []) or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        rows.append({"snapshot_date": ms_to_date(item[0]), f"{coin_id}_usd": as_float(item[1])})
    return pd.DataFrame(rows).drop_duplicates("snapshot_date") if rows else pd.DataFrame(columns=["snapshot_date", f"{coin_id}_usd"])


def row_as_dict(row: pd.Series | None) -> dict | None:
    if row is None:
        return None
    result: dict[str, float | None] = {}
    for key, value in row.to_dict().items():
        if key in ("snapshot_date", "thesis_status", "note"):
            continue
        result[key] = as_float(value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Solana historical fundamentals")
    parser.add_argument("--days", type=int, default=1095, help="Anzahl Tage rueckwirkend, z. B. 365, 1095, 1825")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pause zwischen API-Calls")
    args = parser.parse_args()

    days = max(30, int(args.days))
    today = dt.date.today()
    start = today - dt.timedelta(days=days)

    print(f"Backfill Solana Monitor 3.0: {start.isoformat()} bis {today.isoformat()} ({days} Tage)")

    print("Lade TVL von DeFiLlama...")
    tvl = fetch_defillama_tvl()
    time.sleep(args.sleep)

    print("Lade Stablecoins von DeFiLlama...")
    stablecoins = fetch_stablecoins()
    time.sleep(args.sleep)

    print("Lade DEX Volumen von DeFiLlama...")
    dex_volume = fetch_dex_volume()
    time.sleep(args.sleep)

    print("Lade App Fees von DeFiLlama...")
    app_fees = fetch_app_fees()
    time.sleep(args.sleep)

    print("Lade App Revenue von DeFiLlama...")
    app_revenue = fetch_app_revenue()
    time.sleep(args.sleep)

    print("Lade SOL Preis von CoinGecko...")
    sol_df = fetch_coin_market_chart("solana", days + 5).rename(columns={"solana_usd": "sol_usd"})
    time.sleep(args.sleep)

    print("Lade BTC Preis von CoinGecko...")
    btc_df = fetch_coin_market_chart("bitcoin", days + 5).rename(columns={"bitcoin_usd": "btc_usd"})
    time.sleep(args.sleep)

    df = sol_df.merge(btc_df, on="snapshot_date", how="outer")
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df[(df["snapshot_date"].dt.date >= start) & (df["snapshot_date"].dt.date <= today)]
    df = df.sort_values("snapshot_date")

    if df.empty:
        raise RuntimeError("Keine historischen Preisreihen geladen. Backfill abgebrochen.")

    # Bestehende Historie fuer Vergleichsdaten laden, danach waechst `previous_rows` waehrend des Backfills.
    history = load_history(days=days + 60)
    previous_rows: list[dict[str, Any]] = []
    if not history.empty and "snapshot_date" in history.columns:
        history["snapshot_date"] = pd.to_datetime(history["snapshot_date"])
        for _, old in history.sort_values("snapshot_date").iterrows():
            previous_rows.append({"snapshot_date": old["snapshot_date"].date(), "data": row_as_dict(old)})

    saved = 0
    for _, r in df.iterrows():
        date = r["snapshot_date"].date()
        date_str = date.isoformat()
        sol_usd = as_float(r.get("sol_usd"))
        btc_usd = as_float(r.get("btc_usd"))
        sol_btc = sol_usd / btc_usd if sol_usd and btc_usd else None

        tvl_usd = tvl.get(date_str)
        stablecoins_usd = stablecoins.get(date_str)
        dex_volume_usd = dex_volume.get(date_str)
        fees_usd = app_fees.get(date_str)
        revenue_usd = app_revenue.get(date_str)
        tvl_sol = tvl_usd / sol_usd if tvl_usd and sol_usd else None

        current = {
            "sol_usd": sol_usd,
            "sol_btc": sol_btc,
            "btc_usd": btc_usd,
            "btc_dominance": None,
            "tvl_usd": tvl_usd,
            "tvl_sol": tvl_sol,
            "stablecoins_usd": stablecoins_usd,
            "rwa_usd": None,
            "dex_volume_usd": dex_volume_usd,
            "fees_usd": fees_usd,
            "revenue_usd": revenue_usd,
            "app_fees_usd": fees_usd,
            "app_revenue_usd": revenue_usd,
            "chain_fees_usd": None,
            "chain_revenue_usd": None,
            "active_addresses": None,
        }

        past = None
        past_cutoff = date - dt.timedelta(days=30)
        for old in reversed(previous_rows):
            if old["snapshot_date"] <= past_cutoff:
                past = old["data"]
                break

        result = compute_fundamental_score(current, past)

        row = {
            "snapshot_date": date_str,
            **current,
            "fundamental_score": result["score"],
            "thesis_status": result["status"],
            "note": result.get("note"),
        }

        upsert_row(row)
        previous_rows.append({"snapshot_date": date, "data": current})
        saved += 1

        if saved % 25 == 0 or saved == 1:
            sol_display = f"{sol_usd:.2f}" if sol_usd else "n/a"
            print(f"{date_str}: gespeichert | SOL {sol_display} | Score {result['score']:.0f}")

    print(f"Backfill fertig: {saved} Zeilen gespeichert.")
    print("Letzte Interpretation:")
    print(interpretation_text(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
