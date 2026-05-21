from __future__ import annotations

import os
import uuid

import streamlit as st


def _default_account_id() -> int | None:
    raw_value = os.getenv("CHATBOT_DEFAULT_ACCOUNT_ID", "101").strip()
    if not raw_value:
        return None
    try:
        account_id = int(raw_value)
    except ValueError:
        return None
    return account_id if account_id > 0 else None


def init_chat_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "graph_messages" not in st.session_state:
        st.session_state.graph_messages = []
    if "ticket_counter" not in st.session_state:
        st.session_state.ticket_counter = 1000
    if "user_id" not in st.session_state:
        st.session_state.user_id = os.getenv("CHATBOT_DEFAULT_USER_ID", "seed-user")
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"chat-{uuid.uuid4().hex[:12]}"
    if "account_id" not in st.session_state:
        st.session_state.account_id = _default_account_id()


def reset_chat_state(ticket_start: int = 1000) -> None:
    st.session_state.messages = []
    st.session_state.graph_messages = []
    st.session_state.ticket_counter = ticket_start
    st.session_state.session_id = f"chat-{uuid.uuid4().hex[:12]}"
