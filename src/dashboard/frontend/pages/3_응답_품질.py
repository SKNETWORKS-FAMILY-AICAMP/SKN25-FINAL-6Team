"""Response quality page."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.frontend.views import DashboardClient, inject_dashboard_css, render_quality_section


st.set_page_config(page_title="응답 품질", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("응답 품질")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=1, max_value=365, value=30, step=1, key="quality_days")

client = DashboardClient(api_base_url())

try:
    summary = client.quality(days)
except requests.RequestException as exc:
    st.error(f"응답 품질을 불러오지 못했습니다. {exc}")
    st.stop()

render_quality_section(summary)
