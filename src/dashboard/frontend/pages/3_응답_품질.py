"""Response quality page."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.frontend.state.session_state import api_base_url, init_session_state
from src.dashboard.visualization.charts import as_bar_chart, as_table_rows


st.set_page_config(page_title="응답 품질", layout="wide")
init_session_state()

st.title("응답 품질")

with st.sidebar:
    st.text_input("API URL", key="dashboard_api_base_url")
    days = st.slider("조회 기간(일)", min_value=7, max_value=180, value=30, step=7, key="quality_days")


def _api_get(path: str, params: dict[str, object] | None = None) -> Any:
    response = requests.get(f"{api_base_url()}{path}", params=params, timeout=20)
    response.raise_for_status()
    return response.json()


try:
    summary = _api_get("/summary/quality", {"days": days})
except requests.RequestException as exc:
    st.error(f"응답 품질 요약을 불러오지 못했습니다: {exc}")
    st.stop()

draft = summary["draft_summary"]
evidence = summary["evidence_summary"]
safety = summary["safety_summary"]
final_response = summary["final_response_summary"]
coverage = summary["coverage_metrics"]

metric_cols = st.columns(4)
metric_cols[0].metric("초안 수", draft["draft_count"] or 0)
metric_cols[1].metric("근거 연결 초안", draft["evidence_linked_drafts"] or 0)
metric_cols[2].metric("최종 응답", final_response["final_response_count"] or 0)
metric_cols[3].metric("안전성 평가", safety["safety_check_count"] or 0)

metric_cols = st.columns(4)
metric_cols[0].metric("초안 티켓률", f"{coverage['draft_ticket_rate']:.1%}")
metric_cols[1].metric("근거 첨부율", f"{coverage['evidence_attachment_rate']:.1%}")
metric_cols[2].metric("최종 응답률", f"{coverage['final_response_ticket_rate']:.1%}")
metric_cols[3].metric(
    "평균 최종 지연",
    "-"
    if final_response["avg_final_latency_minutes"] is None
    else f"{final_response['avg_final_latency_minutes']:.1f} min",
)

left, right = st.columns(2, gap="large")
with left:
    render_chart_box("알림 상태", as_bar_chart(summary["notification_summary"]))
    render_chart_box("근거 연결", as_bar_chart([{"label": "evidence", "value": evidence["evidence_count"] or 0}]))

with right:
    render_chart_box(
        "안전성 평균",
        as_bar_chart(
            [
                {"label": "hallucination", "value": safety["avg_hallucination_score"] or 0},
                {"label": "toxicity", "value": safety["avg_toxicity_score"] or 0},
                {"label": "policy_violation", "value": safety["avg_policy_violation_score"] or 0},
                {"label": "factuality", "value": safety["avg_factuality_score"] or 0},
            ]
        ),
    )

st.subheader("품질 점검 후보")
render_data_table(
    as_table_rows(
        summary["quality_candidates"],
        [
            "ticket_id",
            "title",
            "draft_id",
            "hallucination_score",
            "toxicity_score",
            "policy_violation_score",
            "factuality_score",
            "safety_action",
        ],
    )
)
