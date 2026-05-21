from __future__ import annotations

import streamlit as st


def init_chat_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "graph_messages" not in st.session_state:
        st.session_state.graph_messages = []
    if "ticket_counter" not in st.session_state:
        st.session_state.ticket_counter = 1000
    if "user_id" not in st.session_state:
        st.session_state.user_id = "seed-user"
    if "session_id" not in st.session_state:
        st.session_state.session_id = "seed-session"


def reset_chat_state(ticket_start: int = 1000) -> None:
    st.session_state.messages = []
    st.session_state.graph_messages = []
    st.session_state.ticket_counter = ticket_start
