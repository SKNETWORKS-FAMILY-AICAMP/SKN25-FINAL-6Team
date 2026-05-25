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

col_load, col_run = st.columns([1, 1])
if col_load.button("불러오기", type="primary", use_container_width=True):
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

    if not detail["drafts"]:
        st.info("검수할 답변 초안이 없습니다. 워크플로우를 실행하면 초안이 생성됩니다.")
        if col_run.button("워크플로우 실행", use_container_width=True):
            with st.spinner("워크플로우 실행 중..."):
                try:
                    # timeout=120: LangGraph 워크플로우 실행 최대 대기 시간 — LLM 다단계 호출 포함
                    run_resp = requests.post(
                        f"{api_base_url()}/tickets/{st.session_state.selected_ticket_id}/run-workflow",
                        timeout=120,
                    )
                    run_resp.raise_for_status()
                    result = run_resp.json()
                    st.success(f"완료: status={result.get('status')}, draft_id={result.get('draft_id')}")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"워크플로우 실행 실패: {exc}")
    else:
        render_answer_panel(api_base_url(), detail["drafts"][0], reviewer_id or None)
