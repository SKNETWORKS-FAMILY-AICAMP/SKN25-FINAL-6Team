"""Session-state helpers for the operation Streamlit UI."""

from __future__ import annotations

import os

import streamlit as st


# OPERATION_API_BASE_URL 환경변수 우선 — run.py가 실행 시 주입한다
# 환경변수 없으면 로컬 개발 기본값(127.0.0.1:8001)을 사용한다
DEFAULT_API_BASE_URL = os.environ.get("OPERATION_API_BASE_URL", "http://127.0.0.1:8001")


def init_session_state() -> None:
    """Streamlit 세션 상태를 초기화합니다.

    operation_api_base_url: 사이드바에서 변경 가능한 API URL
    selected_ticket_id: 현재 상세 보기 중인 티켓 ID
    """
    if "operation_api_base_url" not in st.session_state:
        st.session_state.operation_api_base_url = DEFAULT_API_BASE_URL
    if "selected_ticket_id" not in st.session_state:
        st.session_state.selected_ticket_id = None


def api_base_url() -> str:
    """현재 세션의 API 기준 URL을 반환합니다. 말미 슬래시를 제거합니다."""
    return str(st.session_state.operation_api_base_url).rstrip("/")
