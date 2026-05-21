"""Streamlit page for answer draft review."""

from __future__ import annotations

import requests
import streamlit as st

from src.operation.frontend.components.answer_panel import render_answer_panel
from src.operation.frontend.state.session_state import api_base_url, init_session_state


st.set_page_config(page_title="답변 검수", layout="wide")
init_session_state()

st.title("답변 검수")

ticket_id = st.number_input("문의 ID", min_value=1, step=1)
reviewer_id = st.text_input("검수자 ID")

if st.button("불러오기", type="primary"):
    st.session_state.selected_ticket_id = int(ticket_id)

if st.session_state.selected_ticket_id:
    try:
        response = requests.get(f"{api_base_url()}/tickets/{st.session_state.selected_ticket_id}", timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"문의 상세를 불러오지 못했습니다: {exc}")
        st.stop()

    detail = response.json()
    ticket = detail["ticket"] or {}
    st.write(ticket.get("raw_query") or "")
    if detail["drafts"]:
        render_answer_panel(api_base_url(), detail["drafts"][0], reviewer_id or None)
    else:
        st.info("검수할 답변 초안이 없습니다.")
