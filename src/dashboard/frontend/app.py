"""Streamlit entry page for the dashboard."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.visualization.charts import as_bar_chart, as_line_chart, as_table_rows


st.set_page_config(page_title="운영 대시보드", layout="wide")
init_session_state()

st.title("운영 대시보드")
st.caption("PostgreSQL 운영 데이터를 기반으로 한 요약 대시보드")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=7, max_value=180, value=30, step=7)
    ticket_limit = st.slider("최근 티켓 수", min_value=10, max_value=50, value=15, step=5)


def _api_get(path: str, params: dict[str, object] | None = None) -> Any:
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=20)
    response.raise_for_status()
    return response.json()


try:
    overview = _api_get("/summary/overview", {"days": days})
except requests.RequestException as exc:
    st.error(f"대시보드 요약을 불러오지 못했습니다: {exc}")
    st.stop()

ticket_counts = overview["ticket_counts"]
response_metrics = overview["response_metrics"]

metric_cols = st.columns(4)
metric_cols[0].metric("전체 티켓", ticket_counts["total"])
metric_cols[1].metric("대기", ticket_counts["pending"])
metric_cols[2].metric("종료", ticket_counts["closed"])
metric_cols[3].metric("오늘 접수", ticket_counts["today"])

metric_cols = st.columns(4)
metric_cols[0].metric("응답률", f"{response_metrics['response_rate']:.1%}")
metric_cols[1].metric("초안 커버리지", f"{response_metrics['draft_coverage_rate']:.1%}")
metric_cols[2].metric("분석 커버리지", f"{response_metrics['analysis_coverage_rate']:.1%}")
metric_cols[3].metric(
    "평균 응답 지연",
    "-" if response_metrics["avg_response_latency_minutes"] is None else f"{response_metrics['avg_response_latency_minutes']:.1f} min",
)

left, right = st.columns(2, gap="large")

with left:
    render_chart_box("접수 채널", as_bar_chart(overview["source_distribution"]))
    render_chart_box("상태 분포", as_bar_chart(overview["status_distribution"]))

with right:
    render_chart_box("라우팅 타깃", as_bar_chart(overview["routing_distribution"]))
    render_chart_box(
        "최근 티켓 추이",
        as_line_chart(overview["recent_tickets"], x_key="inquiry_created_at", y_key="ticket_id"),
        kind="line",
    )

st.subheader("최근 티켓")
render_data_table(as_table_rows(overview["recent_tickets"], [
    "ticket_id",
    "title",
    "status",
    "source_type",
    "nickname",
    "category",
    "risk_level",
    "routing_target",
    "inquiry_created_at",
]))
