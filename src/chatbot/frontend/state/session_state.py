from __future__ import annotations

import time

import streamlit as st


TRACKED_STATE_FIELDS = (
    "ticket_id",
    "user_id",
    "account_id",
    "session_id",
    "raw_query",
    "enriched_query",
    "category",
    "routing_target",
    "classification_method",
    "classification_reason",
    "intent_relation",
    "active_issue_summary",
    "needs_retrieval",
    "retrieval_type",
    "selected_context",
    "analysis_id",
    "draft_id",
    "draft_text",
    "final_text",
    "safety_action",
    "review_required",
)


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
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "game_id" not in st.session_state:
        st.session_state.game_id = ""
    if "email" not in st.session_state:
        st.session_state.email = ""
    if "server_region" not in st.session_state:
        st.session_state.server_region = ""
    if "login_message" not in st.session_state:
        st.session_state.login_message = ""
    if "user_id" in st.session_state and st.session_state.user_id is not None:
        st.session_state.user_id = _coerce_positive_int(st.session_state.user_id)
    if "session_id" not in st.session_state:
        st.session_state.session_id = int(time.time())
    else:
        st.session_state.session_id = _coerce_positive_int(st.session_state.session_id)
    if "account_id" not in st.session_state:
        st.session_state.account_id = None
    else:
        st.session_state.account_id = _coerce_optional_positive_int(st.session_state.account_id)
    if "pending_user_input" not in st.session_state:
        st.session_state.pending_user_input = None
    if "pending_ticket_id" not in st.session_state:
        st.session_state.pending_ticket_id = None
    for field in TRACKED_STATE_FIELDS:
        if field not in st.session_state:
            st.session_state[field] = None


def set_login_state(login_result: dict) -> None:
    st.session_state.logged_in = bool(login_result.get("login_success"))
    st.session_state.user_id = _coerce_positive_int(login_result.get("user_id"))
    st.session_state.account_id = _coerce_optional_positive_int(login_result.get("account_id"))
    st.session_state.game_id = str(login_result.get("game_id") or "")
    st.session_state.email = str(login_result.get("email") or "")
    st.session_state.server_region = str(login_result.get("server_region") or "")
    st.session_state.session_id = int(time.time())
    st.session_state.login_message = str(login_result.get("message") or "")
    reset_chat_state()


def clear_login_state() -> None:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.account_id = None
    st.session_state.game_id = ""
    st.session_state.email = ""
    st.session_state.server_region = ""
    st.session_state.login_message = ""
    reset_chat_state()


def update_state_from_chatbot(result_state: dict) -> None:
    for field in TRACKED_STATE_FIELDS:
        if field in result_state:
            st.session_state[field] = result_state[field]


def reset_chat_state(ticket_start: int = 1000) -> None:
    st.session_state.messages = []
    st.session_state.graph_messages = []
    st.session_state.pending_user_input = None
    st.session_state.pending_ticket_id = None
    st.session_state.ticket_counter = ticket_start
    st.session_state.session_id = _coerce_positive_int(st.session_state.get("session_id", 1))
    for field in TRACKED_STATE_FIELDS:
        if field not in ("user_id", "account_id", "session_id"):
            st.session_state[field] = None
