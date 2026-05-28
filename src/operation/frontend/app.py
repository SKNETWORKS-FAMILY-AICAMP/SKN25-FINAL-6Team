"""Streamlit entry page for operation ticket review."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from src.operation.frontend.components.answer_panel import render_answer_panel
from src.operation.frontend.components.safety_result_box import render_safety_result_box
from src.operation.frontend.components.ticket_card import render_ticket_card
from src.operation.frontend.state.session_state import api_base_url, init_session_state


st.set_page_config(page_title="운영자 문의 검수", layout="wide")
init_session_state()

st.title("운영자 문의 검수")

with st.sidebar:
    st.text_input("API URL", key="operation_api_base_url")
    reviewer_id = st.text_input("검수자 ID")
    list_scope = st.selectbox(
        "문의 목록",
        ["오늘 확인할 문의", "대기 중 문의", "종료된 문의", "전체 문의"],
        index=0,
    )
    limit = st.slider("조회 개수", min_value=10, max_value=200, value=50, step=10)


def _api_get(path: str, params: dict[str, object] | None = None) -> Any:
    # timeout=15: 일반 API 읽기 요청 타임아웃 (초) — 워크플로우 실행은 2_답변_생성.py에서 120초 별도 적용
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _load_ticket_list() -> list[dict[str, Any]]:
    params: dict[str, object] = {"limit": limit}
    if list_scope == "오늘 확인할 문의":
        params["status"] = "pending"
        return _api_get("/tickets/today", params)
    if list_scope == "대기 중 문의":
        params["status"] = "pending"
    elif list_scope == "종료된 문의":
        params["status"] = "closed"
    return _api_get("/tickets", params)


try:
    tickets = _load_ticket_list()
except requests.RequestException as exc:
    st.error(f"문의 목록을 불러오지 못했습니다: {exc}")
    st.stop()

left, right = st.columns([0.9, 1.4], gap="large")

with left:
    st.subheader(list_scope)
    st.caption(f"{len(tickets)}건")
    if not tickets:
        st.info("표시할 문의가 없습니다.")
    for ticket in tickets:
        render_ticket_card(ticket)
        if st.button("상세 확인", key=f"select_{ticket['ticket_id']}", use_container_width=True):
            st.session_state.selected_ticket_id = ticket["ticket_id"]
            st.rerun()

with right:
    selected_ticket_id = st.session_state.selected_ticket_id
    if not selected_ticket_id:
        st.info("왼쪽 문의 목록에서 검수할 문의를 선택하세요.")
    else:
        try:
            detail = _api_get(f"/tickets/{selected_ticket_id}")
        except requests.RequestException as exc:
            st.error(f"문의 상세를 불러오지 못했습니다: {exc}")
            st.stop()

        ticket = detail["ticket"] or {}
        st.subheader(f"문의 상세 #{selected_ticket_id}")
        st.markdown(f"**{ticket.get('title') or '(제목 없음)'}**")
        st.write(ticket.get("raw_query") or "")

        info_cols = st.columns(4)
        info_cols[0].metric("상태", ticket.get("status") or "-")
        info_cols[1].metric("채널", ticket.get("source_type") or "-")
        info_cols[2].metric("닉네임", ticket.get("nickname") or "-")
        info_cols[3].metric("계정", ticket.get("account_id") or "-")

        latest_analysis = detail["analyses"][0] if detail["analyses"] else None
        if latest_analysis:
            with st.container(border=True):
                st.markdown("**분석 결과**")
                st.write(latest_analysis.get("summary") or "")
                st.caption(
                    f"route={latest_analysis.get('category') or '-'} / "
                    f"target={latest_analysis.get('routing_target') or '-'} / "
                    f"risk={latest_analysis.get('risk_level') or '-'}"
                )

        latest_safety = detail["safety_results"][0] if detail["safety_results"] else None
        render_safety_result_box(latest_safety)

        if detail["evidence_docs"]:
            with st.expander("근거 문서", expanded=False):
                for evidence in detail["evidence_docs"]:
                    st.markdown(f"**{evidence.get('source_type') or '-'} / rank {evidence.get('retrieval_rank')}**")
                    st.write(evidence.get("evidence_text") or "")

        if detail["drafts"]:
            render_answer_panel(api_base_url(), detail["drafts"][0], reviewer_id or None)
        else:
            st.info("검수할 답변 초안이 없습니다.")

        if detail["review_logs"]:
            with st.expander("검수 이력", expanded=False):
                st.dataframe(detail["review_logs"], use_container_width=True)
