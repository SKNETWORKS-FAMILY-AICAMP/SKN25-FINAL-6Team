"""Weekly report page."""

from __future__ import annotations

import requests
import streamlit as st

from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.frontend.views import DashboardClient, inject_dashboard_css, render_weekly_report_section


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


st.set_page_config(page_title="Weekly Report", layout="wide")
init_session_state()
inject_dashboard_css()

st.title("Weekly Operations Report")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("Report Window (days)", min_value=1, max_value=365, value=7, step=1, key="weekly_report_days")
    slack_channel = st.text_input("Slack Channel", key="weekly_report_slack_channel", placeholder="#ops-dashboard")
    slack_comment = st.text_area("Slack Comment", key="weekly_report_slack_comment", height=80)

client = DashboardClient(api_base_url())

try:
    report = client.weekly_report(days)
except requests.RequestException as exc:
    st.error(f"Failed to load weekly report: {exc}")
    st.stop()

pdf_state_key = "weekly_pdf_bytes_page"
if pdf_state_key not in st.session_state:
    st.session_state[pdf_state_key] = None

render_weekly_report_section(
    report,
    default_pdf_name=f"dashboard_weekly_report_{days}d.pdf",
)

left, middle, right = st.columns(3, gap="large")
with left:
    if st.button("Generate PDF", use_container_width=True):
        try:
            st.session_state[pdf_state_key] = client.weekly_report_pdf(days)
        except requests.RequestException as exc:
            st.error(f"PDF generation failed: {_error_detail(exc)}")
    if st.session_state[pdf_state_key]:
        st.download_button(
            "Download Generated PDF",
            data=st.session_state[pdf_state_key],
            file_name=f"dashboard_weekly_report_{days}d.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

with middle:
    if st.button("Send Report Now (Default Channel)", use_container_width=True):
        try:
            result = client.send_weekly_report_now(days=days, slack_comment=slack_comment.strip() or None)
            _render_slack_delivery_result(result)
        except requests.RequestException as exc:
            st.error(f"Immediate send failed: {_error_detail(exc)}")

with right:
    if st.button("Send PDF to Selected Channel", use_container_width=True):
        try:
            result = client.send_weekly_report_to_slack(
                days=days,
                slack_channel=slack_channel.strip() or None,
                slack_comment=slack_comment.strip() or None,
            )
            _render_slack_delivery_result(result)
        except requests.RequestException as exc:
            st.error(f"Slack send failed: {_error_detail(exc)}")
