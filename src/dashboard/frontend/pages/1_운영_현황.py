"""Operational status page."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.frontend.views import DashboardClient, inject_dashboard_css, render_overview_section


st.set_page_config(page_title="운영 현황", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("운영 현황")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=1, max_value=365, value=30, step=1, key="ops_days")
    ticket_limit = st.slider("최근 문의 표시 수", min_value=5, max_value=50, value=20, step=5, key="ops_ticket_limit")

client = DashboardClient(api_base_url())

try:
    summary = client.overview(days)
except requests.RequestException as exc:
    st.error(f"운영 현황을 불러오지 못했습니다. {exc}")
    st.stop()

render_overview_section(summary, client, ticket_limit=ticket_limit)
