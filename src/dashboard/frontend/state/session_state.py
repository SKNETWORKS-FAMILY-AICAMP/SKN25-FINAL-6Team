"""Session-state helpers for the dashboard Streamlit UI."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import streamlit as st


DEFAULT_API_BASE_URL = os.environ.get("DASHBOARD_API_BASE_URL") or "http://127.0.0.1:8000"


def _normalize_api_base_url(value: object) -> str:
    raw_url = str(value or "").strip() or DEFAULT_API_BASE_URL
    if "://" not in raw_url:
        raw_url = f"http://{raw_url}"

    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        raw_url = DEFAULT_API_BASE_URL

    return raw_url.rstrip("/")


def init_session_state() -> None:
    if "dashboard_api_base_url" not in st.session_state:
        st.session_state.dashboard_api_base_url = DEFAULT_API_BASE_URL
    if "selected_ticket_id" not in st.session_state:
        st.session_state.selected_ticket_id = None


def api_base_url() -> str:
    return _normalize_api_base_url(st.session_state.dashboard_api_base_url)
