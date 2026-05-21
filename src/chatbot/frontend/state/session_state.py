from __future__ import annotations

import streamlit as st


def _coerce_positive_int(value: object, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_optional_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def init_chat_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "graph_messages" not in st.session_state:
        st.session_state.graph_messages = []
    if "ticket_counter" not in st.session_state:
        st.session_state.ticket_counter = 1000
    if "user_id" not in st.session_state:
        st.session_state.user_id = 1
    else:
        st.session_state.user_id = _coerce_positive_int(st.session_state.user_id)
    if "session_id" not in st.session_state:
        st.session_state.session_id = 1
    else:
        st.session_state.session_id = _coerce_positive_int(st.session_state.session_id)
    if "account_id" not in st.session_state:
        st.session_state.account_id = 101
    else:
        st.session_state.account_id = _coerce_optional_positive_int(st.session_state.account_id)


def reset_chat_state(ticket_start: int = 1000) -> None:
    st.session_state.messages = []
    st.session_state.graph_messages = []
    st.session_state.ticket_counter = ticket_start
    st.session_state.session_id = _coerce_positive_int(st.session_state.get("session_id", 1))
