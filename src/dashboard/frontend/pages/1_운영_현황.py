"""Operational status page."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.frontend.components.metric_card import render_metric_card
from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.visualization.charts import as_bar_chart, as_table_rows


st.set_page_config(page_title="운영 현황", layout="wide")
init_session_state()

st.title("운영 현황")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=7, max_value=180, value=30, step=7, key="ops_days")
    ticket_limit = st.slider("최근 문의 수", min_value=10, max_value=50, value=20, step=5, key="ops_limit")


def _api_get(path: str, params: dict[str, object] | None = None) -> Any:
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=20)
    response.raise_for_status()
    return response.json()


try:
    summary = _api_get("/summary/overview", {"days": days})
except requests.RequestException as exc:
    st.error(f"운영 현황을 불러오지 못했습니다: {exc}")
    st.stop()

counts = summary["ticket_counts"]
response_metrics = summary["response_metrics"]

metric_cols = st.columns(4)
metric_cols[0].metric("전체", counts["total"])
metric_cols[1].metric("대기", counts["pending"])
metric_cols[2].metric("종료", counts["closed"])
metric_cols[3].metric("오늘", counts["today"])

metric_cols = st.columns(4)
metric_cols[0].metric("응답률", f"{response_metrics['response_rate']:.1%}")
metric_cols[1].metric("초안률", f"{response_metrics['draft_coverage_rate']:.1%}")
metric_cols[2].metric("분석률", f"{response_metrics['analysis_coverage_rate']:.1%}")
metric_cols[3].metric(
    "평균 응답 지연",
    "-"
    if response_metrics["avg_response_latency_minutes"] is None
    else f"{response_metrics['avg_response_latency_minutes']:.1f} min",
)

left, right = st.columns(2, gap="large")
with left:
    render_chart_box("접수 채널", as_bar_chart(summary["source_distribution"]))
    render_chart_box("상태 분포", as_bar_chart(summary["status_distribution"]))

with right:
    render_chart_box("라우팅 대상", as_bar_chart(summary["routing_distribution"]))
    render_metric_card("조회 기간", f"{days}일")

st.subheader("최근 문의")
render_data_table(
    as_table_rows(
        summary["recent_tickets"][:ticket_limit],
        [
            "ticket_id",
            "title",
            "status",
            "source_type",
            "nickname",
            "category",
            "risk_level",
            "routing_target",
            "inquiry_created_at",
        ],
    )
)
