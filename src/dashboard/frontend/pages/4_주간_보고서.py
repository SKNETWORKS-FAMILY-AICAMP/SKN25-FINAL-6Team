"""Weekly report page."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.session_state import api_base_url, init_session_state
from src.dashboard.util.views import (
    DashboardClient,
    api_error_detail,
    inject_dashboard_css,
    render_slack_delivery_result,
    render_weekly_report_section,
    session_bytes,
)


st.set_page_config(page_title="주간 보고서", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("주간 보고서")

control_cols = st.columns([1.5, 1, 1, 1], gap="large")
with control_cols[0]:
    st.text_input("API 주소", key="dashboard_api_base_url")
with control_cols[1]:
    days = st.slider("보고서 기준 기간", min_value=1, max_value=365, value=7, step=1, key="weekly_report_days")
with control_cols[2]:
    slack_channel = st.text_input("전송할 슬랙 채널", key="weekly_report_slack_channel", placeholder="#ops-dashboard")
with control_cols[3]:
    slack_comment = st.text_area("추가 메모", key="weekly_report_slack_comment", height=80)

client = DashboardClient(api_base_url())

try:
    report = client.weekly_report(days)
except requests.RequestException as exc:
    st.error(f"주간 보고서를 불러오지 못했습니다. {exc}")
    st.stop()

pdf_state_key = "weekly_pdf_bytes_page"
session_bytes(pdf_state_key)

render_weekly_report_section(
    report,
    default_pdf_name=f"dashboard_weekly_report_{days}d.pdf",
)

left, middle, right = st.columns(3, gap="large")
with left:
    if st.button("주간 보고서 PDF 만들기", use_container_width=True):
        try:
            st.session_state[pdf_state_key] = client.weekly_report_pdf(days)
        except requests.RequestException as exc:
            st.error(f"PDF를 만들지 못했습니다. {api_error_detail(exc)}")
    if st.session_state[pdf_state_key]:
        st.download_button(
            "PDF 내려받기",
            data=st.session_state[pdf_state_key],
            file_name=f"dashboard_weekly_report_{days}d.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

with middle:
    if st.button("기본 채널로 바로 보내기", use_container_width=True):
        try:
            result = client.send_weekly_report_now(days=days, slack_comment=slack_comment.strip() or None)
            render_slack_delivery_result(result)
        except requests.RequestException as exc:
            st.error(f"즉시 전송에 실패했습니다. {api_error_detail(exc)}")

with right:
    if st.button("선택 채널로 PDF 보내기", use_container_width=True):
        try:
            result = client.send_weekly_report_to_slack(
                days=days,
                slack_channel=slack_channel.strip() or None,
                slack_comment=slack_comment.strip() or None,
            )
            render_slack_delivery_result(result)
        except requests.RequestException as exc:
            st.error(f"슬랙 전송에 실패했습니다. {api_error_detail(exc)}")
