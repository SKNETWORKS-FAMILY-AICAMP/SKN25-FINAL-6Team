"""Risk analysis page."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.visualization.charts import as_bar_chart, as_table_rows


st.set_page_config(page_title="리스크 분석", layout="wide")
init_session_state()

st.title("리스크 분석")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=7, max_value=180, value=30, step=7, key="risk_days")


def _api_get(path: str, params: dict[str, object] | None = None) -> Any:
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=20)
    response.raise_for_status()
    return response.json()


try:
    summary = _api_get("/summary/risk", {"days": days})
except requests.RequestException as exc:
    st.error(f"리스크 요약을 불러오지 못했습니다: {exc}")
    st.stop()

safety = summary["safety_score_summary"]
metric_cols = st.columns(4)
metric_cols[0].metric("평균 환각", "-" if safety["avg_hallucination_score"] is None else f"{safety['avg_hallucination_score']:.2f}")
metric_cols[1].metric("평균 유해성", "-" if safety["avg_toxicity_score"] is None else f"{safety['avg_toxicity_score']:.2f}")
metric_cols[2].metric("평균 정책 위반", "-" if safety["avg_policy_violation_score"] is None else f"{safety['avg_policy_violation_score']:.2f}")
metric_cols[3].metric("평균 사실성", "-" if safety["avg_factuality_score"] is None else f"{safety['avg_factuality_score']:.2f}")

left, right = st.columns(2, gap="large")
with left:
    render_chart_box("분석 리스크", as_bar_chart(summary["analysis_risk_distribution"]))
    render_chart_box("감성 분포", as_bar_chart(summary["sentiment_distribution"]))

with right:
    render_chart_box("인사이트 리스크", as_bar_chart(summary["insight_risk_distribution"]))
    render_chart_box("패턴 리스크", as_bar_chart(summary["pattern_risk_distribution"]))

st.subheader("고위험 후보")
render_data_table(
    as_table_rows(
        summary["high_risk_tickets"],
        [
            "ticket_id",
            "title",
            "status",
            "category",
            "risk_level",
            "sentiment",
            "routing_target",
            "pattern_risk_level",
            "inquiry_created_at",
        ],
    )
)
