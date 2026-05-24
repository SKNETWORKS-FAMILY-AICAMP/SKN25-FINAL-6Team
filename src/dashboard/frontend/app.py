"""Streamlit entry page for the dashboard."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.session_state import api_base_url, init_session_state
from src.dashboard.util.views import (
    DashboardClient,
    api_error_detail,
    inject_dashboard_css,
    render_overview_section,
    render_quality_section,
    render_risk_section,
    render_slack_delivery_result,
    render_weekly_report_section,
    session_bytes,
)


st.set_page_config(page_title="운영 현황판", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("운영 현황판")
st.caption("문의 처리 흐름, 위험 신호, 답변 품질, 주간 보고서를 한 화면에서 확인합니다.")

control_cols = st.columns([1.5, 1, 1, 1], gap="large")
with control_cols[0]:
    st.text_input("연결 주소", key="dashboard_api_base_url")
with control_cols[1]:
    days = st.slider("요약을 볼 기간", min_value=1, max_value=365, value=30, step=1, key="dashboard_days")
with control_cols[2]:
    ticket_limit = st.slider("최근 문의 표시 개수", min_value=5, max_value=50, value=20, step=5, key="dashboard_ticket_limit")
with control_cols[3]:
    weekly_days = st.slider("주간 보고서 기준 기간", min_value=1, max_value=365, value=7, step=1, key="dashboard_weekly_days")


client = DashboardClient(api_base_url())

try:
    summary = client.all(days)
except requests.RequestException as exc:
    st.error(f"현황판 데이터를 불러오지 못했습니다. {exc}")
    st.stop()

overview, risk, quality, weekly = st.tabs(["전체 흐름", "위험 신호", "답변 품질", "주간 보고서"])

with overview:
    render_overview_section(summary["overview"], client, ticket_limit=ticket_limit)

with risk:
    render_risk_section(summary["risk"])

with quality:
    render_quality_section(summary["quality"])

with weekly:
    try:
        report = client.weekly_report(weekly_days)
    except requests.RequestException as exc:
        st.error(f"주간 보고서를 불러오지 못했습니다. {exc}")
    else:
        pdf_state_key = "weekly_pdf_bytes_main"
        session_bytes(pdf_state_key)
        render_weekly_report_section(
            report,
            default_pdf_name=f"dashboard_weekly_report_{weekly_days}d.pdf",
        )
        if st.button("보고서 PDF 만들기", use_container_width=True):
            try:
                st.session_state[pdf_state_key] = client.weekly_report_pdf(weekly_days)
            except requests.RequestException as exc:
                st.error(f"PDF를 만들지 못했습니다. {api_error_detail(exc)}")
        if st.session_state[pdf_state_key]:
            st.download_button(
                "만든 PDF 내려받기",
                data=st.session_state[pdf_state_key],
                file_name=f"dashboard_weekly_report_{weekly_days}d.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        slack_comment = st.text_input("바로 보낼 때 덧붙일 말", key="weekly_now_comment")
        if st.button("기본 채널로 지금 보내기", use_container_width=True):
            try:
                result = client.send_weekly_report_now(
                    days=weekly_days,
                    slack_comment=slack_comment.strip() or None,
                )
                render_slack_delivery_result(result)
            except requests.RequestException as exc:
                st.error(f"즉시 전송에 실패했습니다. {api_error_detail(exc)}")
