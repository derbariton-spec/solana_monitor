"""Speicher-Layer: Supabase wenn konfiguriert, sonst lokale CSV-Datei."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from config import LOCAL_CSV, TABLE

load_dotenv()


def supabase_available(write: bool = False) -> bool:
    if not os.getenv("SUPABASE_URL"):
        return False
    if write:
        return bool(os.getenv("SUPABASE_SERVICE_KEY"))
    return bool(os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY"))


def get_supabase_client(write: bool = False):
    from supabase import create_client

    key = os.getenv("SUPABASE_SERVICE_KEY") if write else (os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY"))
    return create_client(os.environ["SUPABASE_URL"], key)


def upsert_row(row: dict[str, Any]) -> None:
    if supabase_available(write=True):
        client = get_supabase_client(write=True)
        client.table(TABLE).upsert(row, on_conflict="snapshot_date").execute()
        return

    path = Path(LOCAL_CSV)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([row])
    if path.exists():
        df = pd.read_csv(path)
        df = df[df["snapshot_date"] != row["snapshot_date"]]
        df = pd.concat([df, new], ignore_index=True)
    else:
        df = new
    df = df.sort_values("snapshot_date")
    df.to_csv(path, index=False)


def load_history(days: int = 365) -> pd.DataFrame:
    if supabase_available(write=False):
        import datetime as dt

        client = get_supabase_client(write=False)
        since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        resp = client.table(TABLE).select("*").gte("snapshot_date", since).order("snapshot_date", desc=False).execute()
        df = pd.DataFrame(resp.data)
    else:
        path = Path(LOCAL_CSV)
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        if not df.empty:
            cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=days)
            df = df[pd.to_datetime(df["snapshot_date"]) >= cutoff]

    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
        df = df.sort_values("snapshot_date")
    return df
