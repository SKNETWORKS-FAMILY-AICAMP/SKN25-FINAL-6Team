"""Streamlit entry page for the dashboard."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.frontend.views import (
    DashboardClient,
    inject_dashboard_css,
    render_overview_section,
    render_quality_section,
    render_risk_section,
    render_weekly_report_section,
)


def _error_detail(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    try:
        payload = response.json()
    except ValueError:
        return str(exc)
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail
    return str(exc)


def _render_slack_delivery_result(result: dict) -> None:
    slack_result = result.get("slack_result", {}) or {}
    delivery_mode = slack_result.get("delivery_mode")
    channel = result.get("channel", "(default channel)")
    if delivery_mode == "fallback_chat_link":
        st.error(f"Slack file share failed for {channel}. Fallback chat link was posted instead.")
    else:
        st.success(f"Slack send completed for {channel}.")
    st.json(slack_result)


st.set_page_config(page_title="Dashboard", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("Operations Dashboard")
st.caption("Ticket operations, risk signals, response quality, and weekly reporting from PostgreSQL data.")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("Summary Window (days)", min_value=1, max_value=365, value=30, step=1, key="dashboard_days")
    ticket_limit = st.slider("Recent Ticket Rows", min_value=5, max_value=50, value=20, step=5, key="dashboard_ticket_limit")
    weekly_days = st.slider("Weekly Report Window (days)", min_value=1, max_value=365, value=7, step=1, key="dashboard_weekly_days")


client = DashboardClient(api_base_url())

try:
    summary = client.all(days)
except requests.RequestException as exc:
    st.error(f"Dashboard API call failed: {exc}")
    st.stop()

overview, risk, quality, weekly = st.tabs(["Overview", "Risk", "Quality", "Weekly Report"])

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
        st.error(f"Weekly report call failed: {exc}")
    else:
        pdf_state_key = "weekly_pdf_bytes_main"
        if pdf_state_key not in st.session_state:
            st.session_state[pdf_state_key] = None
        render_weekly_report_section(
            report,
            default_pdf_name=f"dashboard_weekly_report_{weekly_days}d.pdf",
        )
        if st.button("Generate PDF", use_container_width=True):
            try:
                st.session_state[pdf_state_key] = client.weekly_report_pdf(weekly_days)
            except requests.RequestException as exc:
                st.error(f"PDF generation failed: {_error_detail(exc)}")
        if st.session_state[pdf_state_key]:
            st.download_button(
                "Download Generated PDF",
                data=st.session_state[pdf_state_key],
                file_name=f"dashboard_weekly_report_{weekly_days}d.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        slack_comment = st.text_input("Immediate Send Comment", key="weekly_now_comment")
        if st.button("Send Report Now (Default Channel)", use_container_width=True):
            try:
                result = client.send_weekly_report_now(
                    days=weekly_days,
                    slack_comment=slack_comment.strip() or None,
                )
                _render_slack_delivery_result(result)
            except requests.RequestException as exc:
                st.error(f"Immediate send failed: {_error_detail(exc)}")
