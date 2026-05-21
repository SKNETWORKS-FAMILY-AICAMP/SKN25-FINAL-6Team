"""Streamlit page for operation ticket list."""

from __future__ import annotations

import requests
import streamlit as st

from src.operation.frontend.components.ticket_card import render_ticket_card
from src.operation.frontend.state.session_state import api_base_url, init_session_state


st.set_page_config(page_title="문의 목록", layout="wide")
init_session_state()

st.title("문의 목록")

list_scope = st.selectbox(
    "문의 목록",
    ["오늘 확인할 문의", "대기 중 문의", "종료된 문의", "전체 문의"],
    index=0,
)
limit = st.slider("조회 개수", min_value=10, max_value=200, value=50, step=10)

params: dict[str, object] = {"limit": limit}
path = "/tickets"
if list_scope == "오늘 확인할 문의":
    path = "/tickets/today"
    params["status"] = "pending"
elif list_scope == "대기 중 문의":
    params["status"] = "pending"
elif list_scope == "종료된 문의":
    params["status"] = "closed"

try:
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=15)
    response.raise_for_status()
except requests.RequestException as exc:
    st.error(f"문의 목록을 불러오지 못했습니다: {exc}")
    st.stop()

tickets = response.json()
st.caption(f"{len(tickets)}건")
if not tickets:
    st.info("표시할 문의가 없습니다.")

for ticket in tickets:
    render_ticket_card(ticket)
