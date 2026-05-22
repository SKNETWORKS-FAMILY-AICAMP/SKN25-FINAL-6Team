"""Shared Streamlit rendering helpers for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.util import format_minutes, mask_email, mask_identifier


def as_table_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    return [{column: row.get(column) for column in columns} for row in rows]


def as_bar_chart(rows: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    if "label" not in frame.columns or "value" not in frame.columns:
        return frame
    return frame.set_index("label")[["value"]]


def as_line_chart(rows: list[dict[str, Any]], *, x_key: str, y_key: str) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    if x_key not in frame.columns or y_key not in frame.columns:
        return frame
    frame = frame[[x_key, y_key]].dropna()
    if frame.empty:
        return None
    frame[x_key] = pd.to_datetime(frame[x_key], errors="coerce")
    frame = frame.dropna(subset=[x_key])
    if frame.empty:
        return None
    grouped = frame.groupby(frame[x_key].dt.date)[y_key].count().reset_index(name="count")
    grouped = grouped.rename(columns={x_key: "date"}).set_index("date")
    return grouped


def inject_dashboard_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f7f9;
            color: #18202b;
        }
        .main .block-container {
            max-width: 1440px;
            padding-top: 1.25rem;
            padding-bottom: 2.5rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d7dde5;
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stMetric"] label {
            font-size: 0.8rem;
            color: #667085;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.6rem;
            color: #18202b;
            line-height: 1.2;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border: 1px solid #d7dde5;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        [data-testid="stDataFrame"] {
            border: 1px solid #d7dde5;
            border-radius: 8px;
            overflow: hidden;
        }
        section[data-testid="stSidebar"] {
            background: #111827;
            color: #f9fafb;
        }
        section[data-testid="stSidebar"] * {
            color: #f9fafb;
        }
        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] .stSlider {
            color: #111827;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@dataclass
class DashboardClient:
    """Thin HTTP client for the dashboard API."""

    base_url: str
    timeout: int = 20

    def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def overview(self, days: int) -> dict[str, Any]:
        return self._get("/summary/overview", {"days": days})

    def risk(self, days: int) -> dict[str, Any]:
        return self._get("/summary/risk", {"days": days})

    def quality(self, days: int) -> dict[str, Any]:
        return self._get("/summary/quality", {"days": days})

    def all(self, days: int) -> dict[str, Any]:
        return self._get("/summary/all", {"days": days})

    def tickets(self, params: dict[str, object] | None = None) -> dict[str, Any]:
        return self._get("/tickets", params)

    def ticket_detail(self, ticket_id: int) -> dict[str, Any]:
        return self._get(f"/tickets/{ticket_id}")

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def weekly_report(self, days: int) -> dict[str, Any]:
        return self._get("/reports/weekly", {"days": days})

    def weekly_report_pdf(self, days: int) -> bytes:
        response = requests.get(f"{self.base_url}/reports/weekly/pdf", params={"days": days}, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def send_weekly_report_to_slack(self, *, days: int, slack_channel: str | None, slack_comment: str | None) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/reports/weekly/slack",
            json={"days": days, "slack_channel": slack_channel, "slack_comment": slack_comment},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def send_weekly_report_now(self, *, days: int, slack_comment: str | None = None) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/reports/weekly/slack/now",
            json={"days": days, "slack_comment": slack_comment},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def render_overview_section(summary: dict[str, Any], client: DashboardClient | None = None, *, ticket_limit: int = 20) -> None:
    window = summary.get("window", {})
    counts = summary.get("ticket_counts", {})
    response = summary.get("response_metrics", {})
    coverage = summary.get("coverage_metrics", {})

    st.caption(
        f"조회 범위: 최근 {window.get('days', '-')}일 "
        f"({window.get('window_start', '-') } ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("전체 문의", counts.get("total", 0))
    metric_cols[1].metric("대기", counts.get("pending", 0))
    metric_cols[2].metric("종료", counts.get("closed", 0))
    metric_cols[3].metric("오늘 접수", counts.get("today", 0))

    metric_cols = st.columns(4)
    metric_cols[0].metric("답변율", f"{response.get('response_rate', 0):.1%}")
    metric_cols[1].metric("초안 커버리지", f"{coverage.get('draft_coverage_rate', 0):.1%}")
    metric_cols[2].metric("분석 커버리지", f"{coverage.get('analysis_coverage_rate', 0):.1%}")
    metric_cols[3].metric("평균 답변 지연", format_minutes(response.get("avg_response_latency_minutes")))

    if int(summary.get("old_pending_count") or 0) > 0:
        st.warning(f"24시간을 넘긴 pending 문의가 {summary.get('old_pending_count')}건 있습니다.")

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("접수 채널", as_bar_chart(summary.get("source_distribution", [])))
        render_chart_box("상태 분포", as_bar_chart(summary.get("status_distribution", [])))
    with right:
        render_chart_box("라우팅 분포", as_bar_chart(summary.get("routing_distribution", [])))
        render_chart_box(
            "최근 문의 추이",
            as_line_chart(summary.get("recent_tickets", []), x_key="inquiry_created_at", y_key="ticket_id"),
            kind="line",
        )

    recent_tickets = summary.get("recent_tickets", [])
    st.subheader("최근 문의")
    render_data_table(
        as_table_rows(
            recent_tickets[:ticket_limit],
            [
                "ticket_id",
                "title",
                "status",
                "source_type",
                "nickname",
                "category",
                "risk_level",
                "sentiment",
                "routing_target",
                "inquiry_created_at",
            ],
        )
    )

    if client and recent_tickets:
        st.subheader("문의 상세")
        selected_ticket_id = st.selectbox(
            "상세 확인",
            [row["ticket_id"] for row in recent_tickets],
            format_func=lambda value: f"#{value} {next((row.get('title') for row in recent_tickets if row['ticket_id'] == value), '')}",
        )
        try:
            detail = client.ticket_detail(int(selected_ticket_id))
        except requests.RequestException as exc:
            st.error(f"티켓 상세를 불러오지 못했습니다. {exc}")
            return
        render_ticket_detail(detail)


def render_risk_section(summary: dict[str, Any]) -> None:
    window = summary.get("window", {})
    safety = summary.get("safety_score_summary", {})
    alerts = summary.get("safety_alerts", {})

    st.caption(
        f"조회 범위: 최근 {window.get('days', '-')}일 "
        f"({window.get('window_start', '-') } ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("환각 평균", "-" if safety.get("avg_hallucination_score") is None else f"{safety['avg_hallucination_score']:.2f}")
    metric_cols[1].metric("유해성 평균", "-" if safety.get("avg_toxicity_score") is None else f"{safety['avg_toxicity_score']:.2f}")
    metric_cols[2].metric("정책 위반 평균", "-" if safety.get("avg_policy_violation_score") is None else f"{safety['avg_policy_violation_score']:.2f}")
    metric_cols[3].metric("사실성 평균", "-" if safety.get("avg_factuality_score") is None else f"{safety['avg_factuality_score']:.2f}")

    alert_cols = st.columns(4)
    alert_cols[0].metric("환각 경고", "ON" if alerts.get("high_hallucination") else "OFF")
    alert_cols[1].metric("유해성 경고", "ON" if alerts.get("high_toxicity") else "OFF")
    alert_cols[2].metric("정책 위반 경고", "ON" if alerts.get("high_policy_violation") else "OFF")
    alert_cols[3].metric("사실성 경고", "ON" if alerts.get("low_factuality") else "OFF")

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("분석 위험도", as_bar_chart(summary.get("analysis_risk_distribution", [])))
        render_chart_box("감성 분포", as_bar_chart(summary.get("sentiment_distribution", [])))
    with right:
        render_chart_box("인사이트 위험도", as_bar_chart(summary.get("insight_risk_distribution", [])))
        render_chart_box("패턴 위험도", as_bar_chart(summary.get("pattern_risk_distribution", [])))

    st.subheader("고위험 문의")
    render_data_table(
        as_table_rows(
            summary.get("high_risk_tickets", []),
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

    st.subheader("Safety 위반 후보")
    render_data_table(
        as_table_rows(
            summary.get("safety_breach_candidates", []),
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


def render_quality_section(summary: dict[str, Any]) -> None:
    window = summary.get("window", {})
    draft = summary.get("draft_summary", {})
    evidence = summary.get("evidence_summary", {})
    safety = summary.get("safety_summary", {})
    final_response = summary.get("final_response_summary", {})
    coverage = summary.get("coverage_metrics", {})

    st.caption(
        f"조회 범위: 최근 {window.get('days', '-')}일 "
        f"({window.get('window_start', '-') } ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("초안 수", draft.get("draft_count", 0))
    metric_cols[1].metric("근거 연결 초안", draft.get("evidence_linked_drafts", 0))
    metric_cols[2].metric("최종 답변 수", final_response.get("final_response_count", 0))
    metric_cols[3].metric("Safety 검사 수", safety.get("safety_check_count", 0))
    st.caption(f"초안이 생성된 티켓 수: {draft.get('draft_ticket_count', 0)}")

    metric_cols = st.columns(4)
    metric_cols[0].metric("초안 티켓율", f"{coverage.get('draft_ticket_rate', 0):.1%}")
    metric_cols[1].metric("근거 첨부율", f"{coverage.get('evidence_attachment_rate', 0):.1%}")
    metric_cols[2].metric("최종 답변율", f"{coverage.get('final_response_ticket_rate', 0):.1%}")
    metric_cols[3].metric("최종 답변 지연", format_minutes(final_response.get("avg_final_latency_minutes")))

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("알림 상태", as_bar_chart(summary.get("notification_summary", [])))
        render_chart_box("근거 연결 수", as_bar_chart([{"label": "evidence", "value": evidence.get("evidence_count") or 0}]))
    with right:
        render_chart_box(
            "Safety 평균 점수",
            as_bar_chart(
                [
                    {"label": "hallucination", "value": safety.get("avg_hallucination_score") or 0},
                    {"label": "toxicity", "value": safety.get("avg_toxicity_score") or 0},
                    {"label": "policy_violation", "value": safety.get("avg_policy_violation_score") or 0},
                    {"label": "factuality", "value": safety.get("avg_factuality_score") or 0},
                ]
            ),
        )

    st.subheader("품질 후보")
    render_data_table(
        as_table_rows(
            summary.get("quality_candidates", []),
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

    st.subheader("알림 실패")
    render_data_table(
        as_table_rows(
            summary.get("notification_failures", []),
            [
                "notification_id",
                "ticket_id",
                "title",
                "channel",
                "status",
                "error_category",
                "error_message",
                "sent_at",
            ],
        )
    )


def render_ticket_detail(detail: dict[str, Any]) -> None:
    ticket = detail.get("ticket", {})
    account = detail.get("account", {})
    analyses = detail.get("analyses", [])
    drafts = detail.get("drafts", [])
    evidence_docs = detail.get("evidence_docs", [])
    safety_results = detail.get("safety_results", [])
    final_responses = detail.get("final_responses", [])
    notifications = detail.get("notifications", [])
    voc_feedback = detail.get("voc_feedback", [])
    operation_logs = detail.get("operation_logs", {})
    workflow_logs = detail.get("workflow_logs", {})

    st.markdown(f"### #{ticket.get('ticket_id', '-')}: {ticket.get('title') or '(제목 없음)'}")
    st.write(ticket.get("raw_query") or "")

    info_cols = st.columns(4)
    info_cols[0].metric("상태", ticket.get("status") or "-")
    info_cols[1].metric("채널", ticket.get("source_type") or "-")
    info_cols[2].metric("닉네임", ticket.get("nickname") or mask_identifier(account.get("nickname")))
    info_cols[3].metric("계정", ticket.get("account_id") or "-")

    account_cols = st.columns(4)
    account_cols[0].metric("이메일", mask_email(account.get("email")))
    account_cols[1].metric("UID", account.get("uid") or "-")
    account_cols[2].metric("서버", account.get("server_region") or "-")
    account_cols[3].metric("계정 상태", account.get("account_status") or "-")

    if analyses:
        with st.expander("분석", expanded=True):
            st.dataframe(pd.DataFrame(analyses), use_container_width=True, hide_index=True)
    if drafts:
        with st.expander("초안", expanded=True):
            st.dataframe(pd.DataFrame(drafts), use_container_width=True, hide_index=True)
    if evidence_docs:
        with st.expander("근거 문서", expanded=False):
            st.dataframe(pd.DataFrame(evidence_docs), use_container_width=True, hide_index=True)
    if safety_results:
        with st.expander("Safety", expanded=True):
            st.dataframe(pd.DataFrame(safety_results), use_container_width=True, hide_index=True)
    if final_responses:
        with st.expander("최종 답변", expanded=True):
            st.dataframe(pd.DataFrame(final_responses), use_container_width=True, hide_index=True)
    if notifications:
        with st.expander("알림", expanded=False):
            st.dataframe(pd.DataFrame(notifications), use_container_width=True, hide_index=True)
    if voc_feedback:
        with st.expander("VOC", expanded=False):
            st.dataframe(pd.DataFrame(voc_feedback), use_container_width=True, hide_index=True)

    operation_payload = {
        "payments": operation_logs.get("payments", []),
        "refunds": operation_logs.get("refunds", []),
        "item_delivery_logs": operation_logs.get("item_delivery_logs", []),
        "gacha_logs": operation_logs.get("gacha_logs", []),
    }
    if any(operation_payload.values()):
        with st.expander("업무 로그", expanded=False):
            for key, rows in operation_payload.items():
                if rows:
                    st.markdown(f"**{key}**")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    workflow_payload = {
        "admin_event_logs": workflow_logs.get("admin_event_logs", []),
        "failed_queries": workflow_logs.get("failed_queries", []),
    }
    if any(workflow_payload.values()):
        with st.expander("운영/실패 로그", expanded=False):
            for key, rows in workflow_payload.items():
                if rows:
                    st.markdown(f"**{key}**")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_weekly_report_section(
    report: dict[str, Any],
    *,
    pdf_bytes: bytes | None = None,
    default_pdf_name: str = "dashboard_weekly_report.pdf",
) -> None:
    window = report.get("window", {})
    summary = report.get("summary", {})
    comparisons = report.get("comparisons", {})

    st.caption(
        f"Window: last {window.get('days', '-')} days "
        f"({window.get('window_start', '-')} ~ {window.get('window_end', '-')})"
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric("Analysis", summary.get("analysis_count", 0), delta=comparisons.get("analysis_count", {}).get("change_rate"))
    metric_cols[1].metric("High/Critical", summary.get("high_risk_count", 0), delta=comparisons.get("high_risk_count", {}).get("change_rate"))
    metric_cols[2].metric("Negative Sentiment", summary.get("negative_sentiment_count", 0), delta=comparisons.get("negative_sentiment_count", {}).get("change_rate"))
    metric_cols[3].metric("Human Review", summary.get("human_review_count", 0), delta=comparisons.get("human_review_count", {}).get("change_rate"))

    st.subheader("Narrative Insights")
    for item in report.get("narrative_insights", []):
        st.write(f"- {item}")

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("Category Distribution", as_bar_chart(report.get("category_distribution", [])))
        render_chart_box("Risk Distribution", as_bar_chart(report.get("risk_distribution", [])))
        render_chart_box("Responder Distribution", as_bar_chart(report.get("responder_distribution", [])))
    with right:
        render_chart_box("Sentiment Distribution", as_bar_chart(report.get("sentiment_distribution", [])))
        render_chart_box("Routing Distribution", as_bar_chart(report.get("routing_distribution", [])))
        render_chart_box(
            "Coverage Snapshot",
            as_bar_chart(
                [
                    {"label": "response_rate", "value": summary.get("response_rate", 0)},
                    {"label": "analysis_coverage", "value": summary.get("analysis_coverage_rate", 0)},
                    {"label": "draft_coverage", "value": summary.get("draft_coverage_rate", 0)},
                    {"label": "final_response", "value": summary.get("final_response_ticket_rate", 0)},
                ]
            ),
        )

    st.subheader("Column Insights (ticket_analysis)")
    render_data_table(report.get("column_insights", []))

    st.subheader("Priority Review Tickets")
    render_data_table(
        as_table_rows(
            report.get("review_rows", []),
            [
                "analysis_id",
                "ticket_id",
                "title",
                "category",
                "responder_type",
                "risk_level",
                "sentiment",
                "routing_target",
                "summary",
                "analyzed_at",
            ],
        )
    )

    with st.expander("Full Analysis Rows", expanded=False):
        render_data_table(report.get("analysis_rows", []))

    if pdf_bytes:
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=default_pdf_name,
            mime="application/pdf",
            use_container_width=True,
        )
