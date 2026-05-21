"""Session-state helpers for the dashboard Streamlit UI."""

from __future__ import annotations

import os

import streamlit as st


DEFAULT_API_BASE_URL = os.environ.get("DASHBOARD_API_BASE_URL", "http://127.0.0.1:8000")


def init_session_state() -> None:
    if "dashboard_api_base_url" not in st.session_state:
        st.session_state.dashboard_api_base_url = DEFAULT_API_BASE_URL
    if "selected_ticket_id" not in st.session_state:
        st.session_state.selected_ticket_id = None


def api_base_url() -> str:
    return str(st.session_state.dashboard_api_base_url).rstrip("/")

