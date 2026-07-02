from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import LOCAL_DATA_CSV, load_runtime_config


def ensure_data_dir() -> None:
    Path("data").mkdir(exist_ok=True)


def load_history(days: int = 3650, path: str = LOCAL_DATA_CSV) -> pd.DataFrame:
    ensure_data_dir()
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(file_path)
    if df.empty:
        return df
    if "snapshot_date" in df.columns:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)
        df = df[df["snapshot_date"] >= cutoff].copy()
        df = df.sort_values("snapshot_date")
    return df


def upsert_local_row(row: dict[str, Any], path: str = LOCAL_DATA_CSV) -> None:
    ensure_data_dir()
    file_path = Path(path)
    if file_path.exists():
        df = pd.read_csv(file_path)
    else:
        df = pd.DataFrame()
    row_df = pd.DataFrame([row])
    if df.empty or "snapshot_date" not in df.columns:
        df = row_df
    else:
        df = df[df["snapshot_date"].astype(str) != str(row["snapshot_date"])]
        df = pd.concat([df, row_df], ignore_index=True)
    if "snapshot_date" in df.columns:
        df = df.sort_values("snapshot_date")
    df.to_csv(file_path, index=False)


def upsert_row(row: dict[str, Any]) -> None:
    # V4 keeps fundamentals in versioned CSV for reproducibility. Portfolio is stored in Supabase.
    upsert_local_row(row)


def append_news_rows(rows: list[dict[str, Any]], path: str = "data/news_items.csv") -> None:
    ensure_data_dir()
    file_path = Path(path)
    existing = pd.read_csv(file_path) if file_path.exists() else pd.DataFrame()
    new = pd.DataFrame(rows)
    if existing.empty:
        out = new
    else:
        out = pd.concat([existing, new], ignore_index=True)
        if "link" in out.columns:
            out = out.drop_duplicates(subset=["link"], keep="last")
    out.to_csv(file_path, index=False)
