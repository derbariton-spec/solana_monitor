from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import streamlit as st

from formatting import safe_float


@dataclass
class UserProfile:
    display_name: str = ""
    investor_mode: str = "Public + Personal"
    risk_profile: str = "Ausgewogen"
    onboarding_completed: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UserProfile":
        data = data or {}
        return cls(
            display_name=str(data.get("display_name") or ""),
            investor_mode=str(data.get("investor_mode") or "Public + Personal"),
            risk_profile=str(data.get("risk_profile") or "Ausgewogen"),
            onboarding_completed=bool(data.get("onboarding_completed") or False),
        )

    def to_payload(self, user_id: str) -> dict[str, Any]:
        payload = asdict(self)
        payload["user_id"] = user_id
        return payload


@dataclass
class WatchLevels:
    accumulation_below_usd: float = 150.0
    warning_below_usd: float = 130.0
    hedge_check_above_usd: float = 220.0
    profit_check_above_usd: float = 350.0
    long_term_target_usd: float = 950.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WatchLevels":
        data = data or {}
        return cls(
            accumulation_below_usd=safe_float(data.get("accumulation_below_usd"), 150.0),
            warning_below_usd=safe_float(data.get("warning_below_usd"), 130.0),
            hedge_check_above_usd=safe_float(data.get("hedge_check_above_usd"), 220.0),
            profit_check_above_usd=safe_float(data.get("profit_check_above_usd"), 350.0),
            long_term_target_usd=safe_float(data.get("long_term_target_usd"), 950.0),
        )

    def to_payload(self, user_id: str) -> dict[str, Any]:
        payload = asdict(self)
        payload["user_id"] = user_id
        return payload


@dataclass
class ScenarioPreferences:
    target_prices_csv: str = "250, 500, 950"
    jitosol_apy_assumption: float = 6.5

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScenarioPreferences":
        data = data or {}
        return cls(
            target_prices_csv=str(data.get("target_prices_csv") or "250, 500, 950"),
            jitosol_apy_assumption=safe_float(data.get("jitosol_apy_assumption"), 6.5),
        )

    def to_payload(self, user_id: str) -> dict[str, Any]:
        payload = asdict(self)
        payload["user_id"] = user_id
        return payload


@dataclass
class DailyNote:
    note_date: str = ""
    note: str = ""


def _client_and_user():
    # Local import avoids circular imports: auth imports PositionSettings and streamlit too.
    from auth import current_user, get_supabase_client

    client = get_supabase_client()
    user = current_user()
    if not client or not user:
        return None, None
    return client, user


def _load_single(table: str) -> dict[str, Any] | None:
    client, user = _client_and_user()
    if not client or not user:
        return None
    try:
        response = client.table(table).select("*").eq("user_id", user["id"]).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:
        st.warning(f"{table} konnte nicht geladen werden: {exc}")
        return None


def _upsert_single(table: str, payload: dict[str, Any]) -> bool:
    client, user = _client_and_user()
    if not client or not user:
        st.warning("Bitte anmelden, um persönliche Einstellungen zu speichern.")
        return False
    try:
        payload["user_id"] = user["id"]
        client.table(table).upsert(payload, on_conflict="user_id").execute()
        return True
    except Exception as exc:
        st.error(f"{table} konnte nicht gespeichert werden: {exc}")
        return False


def load_user_profile() -> UserProfile:
    return UserProfile.from_dict(_load_single("user_profiles"))


def save_user_profile(profile: UserProfile) -> bool:
    client, user = _client_and_user()
    if not client or not user:
        st.warning("Bitte anmelden, um dein Profil zu speichern.")
        return False
    return _upsert_single("user_profiles", profile.to_payload(user["id"]))


def load_watch_levels() -> WatchLevels:
    return WatchLevels.from_dict(_load_single("user_watch_levels"))


def save_watch_levels(levels: WatchLevels) -> bool:
    client, user = _client_and_user()
    if not client or not user:
        st.warning("Bitte anmelden, um Watch-Level zu speichern.")
        return False
    return _upsert_single("user_watch_levels", levels.to_payload(user["id"]))


def load_scenario_preferences() -> ScenarioPreferences:
    return ScenarioPreferences.from_dict(_load_single("user_scenarios"))


def save_scenario_preferences(prefs: ScenarioPreferences) -> bool:
    client, user = _client_and_user()
    if not client or not user:
        st.warning("Bitte anmelden, um Szenarien zu speichern.")
        return False
    return _upsert_single("user_scenarios", prefs.to_payload(user["id"]))


def load_recent_notes(limit: int = 20) -> list[dict[str, Any]]:
    client, user = _client_and_user()
    if not client or not user:
        return []
    try:
        response = (
            client.table("user_notes")
            .select("note_date,note,created_at")
            .eq("user_id", user["id"])
            .order("note_date", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        st.warning(f"Notizen konnten nicht geladen werden: {exc}")
        return []


def save_daily_note(note_date: str, note: str) -> bool:
    client, user = _client_and_user()
    if not client or not user:
        st.warning("Bitte anmelden, um Notizen zu speichern.")
        return False
    try:
        payload = {"user_id": user["id"], "note_date": note_date, "note": note}
        client.table("user_notes").upsert(payload, on_conflict="user_id,note_date").execute()
        return True
    except Exception as exc:
        st.error(f"Notiz konnte nicht gespeichert werden: {exc}")
        return False
