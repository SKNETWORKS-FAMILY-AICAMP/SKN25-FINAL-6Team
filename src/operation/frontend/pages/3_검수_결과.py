"""Streamlit page for operation review result history."""

from __future__ import annotations

import requests
import streamlit as st

from src.operation.frontend.state.session_state import api_base_url, init_session_state


st.set_page_config(page_title="검수 결과", layout="wide")
init_session_state()

st.title("검수 결과")

ticket_id = st.number_input("문의 ID", min_value=1, step=1)

if st.button("조회", type="primary"):
    try:
        response = requests.get(f"{api_base_url()}/tickets/{int(ticket_id)}", timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"검수 결과를 불러오지 못했습니다: {exc}")
        st.stop()

    detail = response.json()
    st.subheader("최종 답변")
    st.dataframe(detail["final_responses"], use_container_width=True)
    st.subheader("긴급 알림")
    st.dataframe(detail["notifications"], use_container_width=True)
    st.subheader("검수 이력")
    st.dataframe(detail["review_logs"], use_container_width=True)
