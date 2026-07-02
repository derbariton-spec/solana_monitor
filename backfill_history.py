from __future__ import annotations

import argparse
import datetime as dt
import time
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from data_sources import (
    fetch_historical_dex_volume,
    fetch_historical_fees,
    fetch_historical_stablecoins,
    fetch_historical_tvl,
)
from scoring import compute_fundamental_score, interpretation_text
from storage import upsert_row

load_dotenv()

REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "solana-monitor-v4-backfill/4.0.1",
    "Accept": "application/json",
}

COINGECKO_RANGE_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
COINGECKO_MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/{product_id}/candles"

COINBASE_PRODUCTS = {
    "solana": "SOL-USD",
    "bitcoin": "BTC-USD",
}


def _get_json(url: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any | None:
    """Small explicit HTTP helper for the backfill.

    It prints failures so GitHub Actions logs show which external source failed.
    """
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                body = (r.text or "")[:300].replace("\n", " ")
                print(f"HTTP {r.status_code} bei {url}: {body}")
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"Request fehlgeschlagen, Versuch {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return None


def _date_from_ms(ms: int | float) -> str:
    return dt.datetime.fromtimestamp(float(ms) / 1000, tz=dt.timezone.utc).date().isoformat()


def _date_from_seconds(seconds: int | float) -> str:
    return dt.datetime.fromtimestamp(float(seconds), tz=dt.timezone.utc).date().isoformat()


def _frame_from_prices(prices: list[Any], column: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in prices or []:
        try:
            ms, price = item
            rows.append({"snapshot_date": _date_from_ms(ms), column: float(price)})
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=["snapshot_date", column])
    return (
        pd.DataFrame(rows)
        .sort_values("snapshot_date")
        .drop_duplicates("snapshot_date", keep="last")
    )


def _fetch_coingecko_range(coin_id: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    column = f"{coin_id}_usd"
    start_dt = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc)
    end_dt = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    url = COINGECKO_RANGE_URL.format(coin_id=coin_id)
    data = _get_json(url, {
        "vs_currency": "usd",
        "from": int(start_dt.timestamp()),
        "to": int(end_dt.timestamp()),
    })
    if not isinstance(data, dict):
        return pd.DataFrame(columns=["snapshot_date", column])
    return _frame_from_prices(data.get("prices", []), column)


def _fetch_coingecko_days(coin_id: str, days: int) -> pd.DataFrame:
    column = f"{coin_id}_usd"
    url = COINGECKO_MARKET_CHART_URL.format(coin_id=coin_id)
    data = _get_json(url, {"vs_currency": "usd", "days": str(days)})
    if not isinstance(data, dict):
        return pd.DataFrame(columns=["snapshot_date", column])
    return _frame_from_prices(data.get("prices", []), column)


def _iso_z(value: dt.datetime) -> str:
    value = value.astimezone(dt.timezone.utc).replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_coinbase_daily(coin_id: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    product_id = COINBASE_PRODUCTS.get(coin_id)
    column = f"{coin_id}_usd"
    if not product_id:
        return pd.DataFrame(columns=["snapshot_date", column])

    rows: list[dict[str, Any]] = []
    cursor = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc)
    final_end = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    url = COINBASE_CANDLES_URL.format(product_id=product_id)

    # Coinbase Exchange erlaubt nur begrenzte Candle-Mengen pro Request.
    # 250 Tage ist bewusst unterhalb des üblichen Limits und damit stabil.
    while cursor < final_end:
        batch_end = min(cursor + dt.timedelta(days=250), final_end)
        data = _get_json(url, {
            "start": _iso_z(cursor),
            "end": _iso_z(batch_end),
            "granularity": 86400,
        }, retries=2)

        if isinstance(data, list):
            for candle in data:
                try:
                    ts, _low, _high, _open, close, _volume = candle
                    rows.append({"snapshot_date": _date_from_seconds(ts), column: float(close)})
                except Exception:
                    continue

        cursor = batch_end
        time.sleep(0.25)

    if not rows:
        return pd.DataFrame(columns=["snapshot_date", column])
    return (
        pd.DataFrame(rows)
        .sort_values("snapshot_date")
        .drop_duplicates("snapshot_date", keep="last")
    )


def fetch_price_history(coin_id: str, days: int, start: dt.date, end: dt.date) -> pd.DataFrame:
    """Fetch coin USD history with several fallbacks.

    1. CoinGecko range endpoint
    2. CoinGecko market_chart endpoint
    3. Coinbase public daily candles for SOL/BTC
    """
    column = f"{coin_id}_usd"

    df = _fetch_coingecko_range(coin_id, start, end)
    print(f"{coin_id}: CoinGecko range rows = {len(df)}")
    if len(df) >= 30:
        return df

    time.sleep(1)
    df = _fetch_coingecko_days(coin_id, days + 5)
    print(f"{coin_id}: CoinGecko days rows = {len(df)}")
    if len(df) >= 30:
        return df

    time.sleep(1)
    df = _fetch_coinbase_daily(coin_id, start, end)
    print(f"{coin_id}: Coinbase daily rows = {len(df)}")
    if len(df) >= 1:
        return df

    print(f"WARNUNG: Keine Preisdaten fuer {coin_id} geladen.")
    return pd.DataFrame(columns=["snapshot_date", column])


def _value(mapping: dict[str, float], date_str: str):
    return mapping.get(date_str)


def _base_dates(start: dt.date, today: dt.date, *mappings: dict[str, float]) -> list[str]:
    dates: set[str] = set()
    for mapping in mappings:
        dates.update(mapping.keys())
    if not dates:
        # Absolute Notfall-Basis: tägliche Datumsreihe, damit trotzdem eine CSV entsteht.
        return [(start + dt.timedelta(days=i)).isoformat() for i in range((today - start).days + 1)]
    return sorted(d for d in dates if start.isoformat() <= d <= today.isoformat())


def main(days: int = 1825) -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    print(f"Backfill Solana history: {start} bis {today}")

    tvl = fetch_historical_tvl(); time.sleep(1)
    stable = fetch_historical_stablecoins(); time.sleep(1)
    dex = fetch_historical_dex_volume(); time.sleep(1)
    app_fees = fetch_historical_fees("dailyFees"); time.sleep(1)
    app_revenue = fetch_historical_fees("dailyRevenue"); time.sleep(1)

    print(f"TVL rows={len(tvl)}, Stablecoin rows={len(stable)}, DEX rows={len(dex)}, Fees rows={len(app_fees)}, Revenue rows={len(app_revenue)}")

    sol_prices = fetch_price_history("solana", days + 5, start, today); time.sleep(1)
    btc_prices = fetch_price_history("bitcoin", days + 5, start, today); time.sleep(1)

    # If all external price sources fail, continue with fundamental rows instead of aborting.
    # The dashboard then still has historical TVL/stablecoin/dex/fees data.
    if sol_prices.empty:
        print("WARNUNG: Keine SOL-Preisdaten geladen. Backfill laeuft ohne SOL-Preis weiter.")
        dates = _base_dates(start, today, tvl, stable, dex, app_fees, app_revenue)
        df = pd.DataFrame({"snapshot_date": dates})
        df["sol_usd"] = None
    else:
        df = sol_prices.rename(columns={"solana_usd": "sol_usd"})

    if btc_prices.empty:
        df["btc_usd"] = None
    else:
        df = df.merge(
            btc_prices.rename(columns={"bitcoin_usd": "btc_usd"}),
            on="snapshot_date",
            how="outer",
        )

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df[(df["snapshot_date"].dt.date >= start) & (df["snapshot_date"].dt.date <= today)].sort_values("snapshot_date")

    previous_rows: list[dict[str, Any]] = []
    written = 0

    for _, r in df.iterrows():
        date = r["snapshot_date"].date()
        date_str = date.isoformat()
        sol_usd = r.get("sol_usd")
        btc_usd = r.get("btc_usd")
        sol_usd = float(sol_usd) if pd.notna(sol_usd) else None
        btc_usd = float(btc_usd) if pd.notna(btc_usd) else None
        sol_btc = (sol_usd / btc_usd) if sol_usd and btc_usd else None

        tvl_usd = _value(tvl, date_str)
        stablecoins_usd = _value(stable, date_str)
        dex_volume_usd = _value(dex, date_str)
        app_fees_usd = _value(app_fees, date_str)
        app_revenue_usd = _value(app_revenue, date_str)
        tvl_sol = (tvl_usd / sol_usd) if tvl_usd and sol_usd else None

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
        upsert_row({
            "snapshot_date": date_str,
            **current,
            "fundamental_score": result["score"],
            "thesis_status": result["status"],
            "note": interpretation_text(result),
        })
        previous_rows.append({"date": date, "data": current})
        written += 1
        print(f"{date_str}: SOL={current['sol_usd']} TVL={current['tvl_usd']} Score={result['score']}")

    print(f"Backfill fertig. Geschriebene Zeilen: {written}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1825, help="Anzahl der Tage fuer den Backfill")
    args = parser.parse_args()
    main(args.days)
