from __future__ import annotations

import datetime as dt
import sys

import pandas as pd
from dotenv import load_dotenv

from data_sources import fetch_snapshot
from scoring import compute_fundamental_score, interpretation_text
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
    return {key: _clean(row.get(key)) for key in row.index if key != "snapshot_date"}


def main() -> None:
    today = dt.date.today()
    print(f"[{today}] Sammle Solana-Daten...")
    current = fetch_snapshot()
    df = load_history(days=3700)
    target = pd.Timestamp(today) - pd.Timedelta(days=30)
    past = None
    if not df.empty and "snapshot_date" in df.columns:
        candidates = df[df["snapshot_date"] <= target]
        if not candidates.empty:
            past = row_as_dict(candidates.iloc[-1])
    result = compute_fundamental_score(current, past)
    row = {"snapshot_date": today.isoformat(), **current, "fundamental_score": result["score"], "thesis_status": result["status"], "note": interpretation_text(result)}
    upsert_row(row)
    print(f"[{today}] Gespeichert. Score: {result['score']}/100 ({result['status']})")
    print(interpretation_text(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
