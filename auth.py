from __future__ import annotations

from typing import Any

import streamlit as st

from config import has_supabase, load_runtime_config
from portfolio import PositionSettings

try:
    from supabase import create_client
except Exception:  # pragma: no cover
    create_client = None


@st.cache_resource(show_spinner=False)
def get_supabase_client():
    cfg = load_runtime_config()
    if not cfg.supabase_url or not cfg.supabase_anon_key or create_client is None:
        return None
    return create_client(cfg.supabase_url, cfg.supabase_anon_key)


def is_logged_in() -> bool:
    return bool(st.session_state.get("user"))


def current_user() -> dict[str, Any] | None:
    return st.session_state.get("user")


def sign_out() -> None:
    st.session_state.pop("user", None)
    st.session_state.pop("access_token", None)
    st.session_state.pop("position_loaded", None)


def render_auth_box() -> None:
    client = get_supabase_client()
    if client is None:
        st.info("Supabase ist nicht konfiguriert. Portfolio-Daten werden nur lokal in der aktuellen Session genutzt.")
        return
    if is_logged_in():
        user = current_user() or {}
        st.success(f"Angemeldet: {user.get('email', 'Nutzer')}")
        if st.button("Logout"):
            sign_out()
            st.rerun()
        return
    mode = st.radio("Login-Modus", ["Einloggen", "Registrieren"], horizontal=True)
    email = st.text_input("E-Mail", key="auth_email")
    password = st.text_input("Passwort", type="password", key="auth_password")
    if st.button("Anmelden" if mode == "Einloggen" else "Account erstellen"):
        if not email or not password:
            st.warning("Bitte E-Mail und Passwort eingeben.")
            return
        try:
            if mode == "Einloggen":
                result = client.auth.sign_in_with_password({"email": email, "password": password})
            else:
                result = client.auth.sign_up({"email": email, "password": password})
            user = result.user
            session = result.session
            st.session_state["user"] = {"id": user.id, "email": user.email}
            if session:
                st.session_state["access_token"] = session.access_token
            st.success("Login erfolgreich.")
            st.rerun()
        except Exception as exc:
            st.error(f"Login fehlgeschlagen: {exc}")


def load_user_position() -> PositionSettings:
    client = get_supabase_client()
    user = current_user()
    if not client or not user:
        return PositionSettings()
    try:
        response = client.table("user_positions").select("*").eq("user_id", user["id"]).limit(1).execute()
        rows = response.data or []
        if rows:
            return PositionSettings.from_dict(rows[0])
    except Exception as exc:
        st.warning(f"Position konnte nicht geladen werden: {exc}")
    return PositionSettings()


def save_user_position(position: PositionSettings) -> bool:
    client = get_supabase_client()
    user = current_user()
    if not client or not user:
        st.warning("Nicht angemeldet oder Supabase nicht konfiguriert.")
        return False
    payload = {
        "user_id": user["id"],
        "wallet_address": position.wallet_address,
        "manual_jitosol_amount": position.manual_jitosol_amount,
        "manual_sol_equivalent": position.manual_sol_equivalent,
        "avg_entry_jitosol_usd": position.avg_entry_jitosol_usd,
        "historical_sol_entry_usd": position.historical_sol_entry_usd,
        "bought_sol_basis": position.bought_sol_basis,
        "staking_start_date": position.staking_start_date or None,
    }
    try:
        client.table("user_positions").upsert(payload, on_conflict="user_id").execute()
        return True
    except Exception as exc:
        st.error(f"Speichern fehlgeschlagen: {exc}")
        return False
