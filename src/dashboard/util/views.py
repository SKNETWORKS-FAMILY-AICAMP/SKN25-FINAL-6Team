"""Shared Streamlit rendering helpers for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.dashboard.frontend.components.chart_box import render_chart_box
from src.dashboard.frontend.components.data_table import render_data_table
from src.dashboard.util.text import SECTION_LABELS, localized_rows, translate_value
from src.dashboard.util import format_minutes, mask_email, mask_identifier


def as_table_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    return [{column: row.get(column) for column in columns} for row in rows]


def as_bar_chart(rows: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    if "label" not in frame.columns or "value" not in frame.columns:
        return frame
    frame["label"] = frame["label"].map(lambda value: translate_value(value, key="label"))
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
    grouped = frame.groupby(frame[x_key].dt.date)[y_key].count().reset_index(name="건수")
    grouped = grouped.rename(columns={x_key: "날짜"}).set_index("날짜")
    return grouped


def api_error_detail(exc: requests.RequestException) -> str:
    """Extract the API detail field when FastAPI returned a structured error."""

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


def render_slack_delivery_result(result: dict[str, Any]) -> None:
    """Show a consistent Slack delivery status block across dashboard pages."""

    slack_result = result.get("slack_result", {}) or {}
    delivery_mode = slack_result.get("delivery_mode")
    channel = result.get("channel", "기본 채널")
    if delivery_mode == "fallback_chat_link":
        st.error(f"{channel}에 파일로 보내지 못해 대화방 링크로 대신 보냈습니다.")
    else:
        st.success(f"{channel}로 보고서를 보냈습니다.")
    st.json(localized_rows([slack_result])[0] if slack_result else {})


def session_bytes(key: str) -> bytes | None:
    """Lazily initialize binary session state used for generated PDFs."""

    if key not in st.session_state:
        st.session_state[key] = None
    return st.session_state[key]


def render_ai_interpretation(payload: dict[str, Any]) -> None:
    """Render an AI-generated interpretation block in consistent Korean UI."""

    interpretation = payload.get("ai_interpretation", {}) or {}
    if not interpretation:
        return
    with st.container(border=True):
        st.markdown(f"### {interpretation.get('headline') or 'AI 해석'}")
        summary = str(interpretation.get("summary") or "").strip()
        if summary:
            st.write(summary)
        bullets = interpretation.get("bullets", [])
        if bullets:
            st.markdown("**AI가 먼저 짚은 내용**")
            for item in bullets:
                st.write(f"- {item}")
        actions = interpretation.get("actions", [])
        if actions:
            st.markdown("**운영팀이 바로 볼 일**")
            for item in actions:
                st.write(f"- {item}")


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
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@dataclass
class DashboardClient:
    """Thin HTTP client for the dashboard API."""

    base_url: str
    connect_timeout: int = 5
    default_read_timeout: int = 30
    report_read_timeout: int = 180

    def _timeout(self, *, report: bool = False) -> tuple[int, int]:
        return (
            self.connect_timeout,
            self.report_read_timeout if report else self.default_read_timeout,
        )

    def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=self._timeout())
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
        response = requests.get(
            f"{self.base_url}/reports/weekly",
            params={"days": days},
            timeout=self._timeout(report=True),
        )
        response.raise_for_status()
        return response.json()

    def weekly_report_pdf(self, days: int) -> bytes:
        response = requests.get(
            f"{self.base_url}/reports/weekly/pdf",
            params={"days": days},
            timeout=self._timeout(report=True),
        )
        response.raise_for_status()
        return response.content

    def send_weekly_report_to_slack(self, *, days: int, slack_channel: str | None, slack_comment: str | None) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/reports/weekly/slack",
            json={"days": days, "slack_channel": slack_channel, "slack_comment": slack_comment},
            timeout=self._timeout(report=True),
        )
        response.raise_for_status()
        return response.json()

    def send_weekly_report_now(self, *, days: int, slack_comment: str | None = None) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/reports/weekly/slack/now",
            json={"days": days, "slack_comment": slack_comment},
            timeout=self._timeout(report=True),
        )
        response.raise_for_status()
        return response.json()


def render_overview_section(summary: dict[str, Any], client: DashboardClient | None = None, *, ticket_limit: int = 20) -> None:
    window = summary.get("window", {})
    counts = summary.get("ticket_counts", {})
    response = summary.get("response_metrics", {})
    coverage = summary.get("coverage_metrics", {})

    render_ai_interpretation(summary)
    st.caption(
        f"최근 {window.get('days', '-')}일을 기준으로 보고 있습니다. "
        f"({window.get('window_start', '-')} ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("전체 문의", counts.get("total", 0))
    metric_cols[1].metric("처리 대기", counts.get("pending", 0))
    metric_cols[2].metric("처리 완료", counts.get("closed", 0))
    metric_cols[3].metric("오늘 들어온 문의", counts.get("today", 0))

    metric_cols = st.columns(4)
    metric_cols[0].metric("답변까지 끝난 비율", f"{response.get('response_rate', 0):.1%}")
    metric_cols[1].metric("초안까지 만든 비율", f"{coverage.get('draft_coverage_rate', 0):.1%}")
    metric_cols[2].metric("분석까지 끝난 비율", f"{coverage.get('analysis_coverage_rate', 0):.1%}")
    metric_cols[3].metric("답변까지 걸린 평균 시간", format_minutes(response.get("avg_response_latency_minutes")))

    if int(summary.get("old_pending_count") or 0) > 0:
        st.warning(f"하루 넘게 처리 대기인 문의가 {summary.get('old_pending_count')}건 있습니다.")

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("어디로 들어온 문의인지", as_bar_chart(summary.get("source_distribution", [])))
        render_chart_box("지금 처리 상태", as_bar_chart(summary.get("status_distribution", [])))
    with right:
        render_chart_box("다음에 어떻게 처리되는지", as_bar_chart(summary.get("routing_distribution", [])))
        render_chart_box(
            "최근 문의가 들어온 흐름",
            as_line_chart(summary.get("recent_tickets", []), x_key="inquiry_created_at", y_key="ticket_id"),
            kind="line",
        )

    recent_tickets = summary.get("recent_tickets", [])
    st.subheader("최근 들어온 문의")
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
        ),
        kind="inbox",
    )

    if client and recent_tickets:
        st.subheader("문의 한 건 자세히 보기")
        selected_ticket_id = st.selectbox(
            "확인할 문의를 고르세요",
            [row["ticket_id"] for row in recent_tickets],
            format_func=lambda value: f"#{value} {next((row.get('title') for row in recent_tickets if row['ticket_id'] == value), '')}",
        )
        try:
            detail = client.ticket_detail(int(selected_ticket_id))
        except requests.RequestException as exc:
            st.error(f"문의 자세한 내용을 불러오지 못했습니다. {exc}")
            return
        render_ticket_detail(detail)


def render_risk_section(summary: dict[str, Any]) -> None:
    window = summary.get("window", {})
    safety = summary.get("safety_score_summary", {})
    alerts = summary.get("safety_alerts", {})

    render_ai_interpretation(summary)
    st.caption(
        f"최근 {window.get('days', '-')}일 동안 위험 신호를 모아 봤습니다. "
        f"({window.get('window_start', '-')} ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("사실과 다른 내용 위험 평균", "-" if safety.get("avg_hallucination_score") is None else f"{safety['avg_hallucination_score']:.2f}")
    metric_cols[1].metric("공격적 표현 위험 평균", "-" if safety.get("avg_toxicity_score") is None else f"{safety['avg_toxicity_score']:.2f}")
    metric_cols[2].metric("운영 정책 위반 위험 평균", "-" if safety.get("avg_policy_violation_score") is None else f"{safety['avg_policy_violation_score']:.2f}")
    metric_cols[3].metric("사실성 평균", "-" if safety.get("avg_factuality_score") is None else f"{safety['avg_factuality_score']:.2f}")

    alert_cols = st.columns(4)
    alert_cols[0].metric("사실과 다른 내용 위험 경고", "켜짐" if alerts.get("high_hallucination") else "꺼짐")
    alert_cols[1].metric("공격적 표현 위험 경고", "켜짐" if alerts.get("high_toxicity") else "꺼짐")
    alert_cols[2].metric("운영 정책 위반 경고", "켜짐" if alerts.get("high_policy_violation") else "꺼짐")
    alert_cols[3].metric("사실성 부족 경고", "켜짐" if alerts.get("low_factuality") else "꺼짐")

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("문의 분석에서 본 위험도", as_bar_chart(summary.get("analysis_risk_distribution", [])))
        render_chart_box("이용자 반응 분위기", as_bar_chart(summary.get("sentiment_distribution", [])))
    with right:
        render_chart_box("인사이트에서 본 위험도", as_bar_chart(summary.get("insight_risk_distribution", [])))
        render_chart_box("반복 패턴에서 본 위험도", as_bar_chart(summary.get("pattern_risk_distribution", [])))

    st.subheader("우선 봐야 할 고위험 문의")
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
        ),
        kind="priority",
    )

    st.subheader("답변 전에 다시 봐야 할 안전성 후보")
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
        ),
        kind="safety",
    )


def render_quality_section(summary: dict[str, Any]) -> None:
    window = summary.get("window", {})
    draft = summary.get("draft_summary", {})
    evidence = summary.get("evidence_summary", {})
    safety = summary.get("safety_summary", {})
    final_response = summary.get("final_response_summary", {})
    coverage = summary.get("coverage_metrics", {})

    render_ai_interpretation(summary)
    st.caption(
        f"최근 {window.get('days', '-')}일 동안 답변 품질을 이렇게 봤습니다. "
        f"({window.get('window_start', '-')} ~ {window.get('window_end', '-')})"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("만든 초안 수", draft.get("draft_count", 0))
    metric_cols[1].metric("근거까지 붙은 초안 수", draft.get("evidence_linked_drafts", 0))
    metric_cols[2].metric("보낸 최종 답변 수", final_response.get("final_response_count", 0))
    metric_cols[3].metric("안전성 점검 수", safety.get("safety_check_count", 0))
    st.caption(f"초안이 만들어진 문의는 {draft.get('draft_ticket_count', 0)}건입니다.")

    metric_cols = st.columns(4)
    metric_cols[0].metric("문의 대비 초안 작성 비율", f"{coverage.get('draft_ticket_rate', 0):.1%}")
    metric_cols[1].metric("초안 대비 근거 첨부 비율", f"{coverage.get('evidence_attachment_rate', 0):.1%}")
    metric_cols[2].metric("문의 대비 최종 답변 완료 비율", f"{coverage.get('final_response_ticket_rate', 0):.1%}")
    metric_cols[3].metric("최종 답변까지 걸린 평균 시간", format_minutes(final_response.get("avg_final_latency_minutes")))

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("알림이 잘 전달됐는지", as_bar_chart(summary.get("notification_summary", [])))
        render_chart_box("붙인 근거 수", as_bar_chart([{"label": "evidence", "value": evidence.get("evidence_count") or 0}]))
    with right:
        render_chart_box(
            "안전성 점수 한눈에 보기",
            as_bar_chart(
                [
                    {"label": "hallucination", "value": safety.get("avg_hallucination_score") or 0},
                    {"label": "toxicity", "value": safety.get("avg_toxicity_score") or 0},
                    {"label": "policy_violation", "value": safety.get("avg_policy_violation_score") or 0},
                    {"label": "factuality", "value": safety.get("avg_factuality_score") or 0},
                ]
            ),
        )

    st.subheader("품질 점검이 필요한 초안")
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
        ),
        kind="quality",
    )

    st.subheader("알림 전송이 실패한 내역")
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
        ),
        kind="failure_log",
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

    st.markdown(f"### 문의 #{ticket.get('ticket_id', '-')}: {ticket.get('title') or '(제목 없음)'}")
    st.write(ticket.get("raw_query") or "")

    info_cols = st.columns(4)
    info_cols[0].metric("처리 상태", translate_value(ticket.get("status"), key="status"))
    info_cols[1].metric("접수 경로", translate_value(ticket.get("source_type"), key="source_type"))
    info_cols[2].metric("이용자 닉네임", ticket.get("nickname") or mask_identifier(account.get("nickname")))
    info_cols[3].metric("계정 번호", ticket.get("account_id") or "-")

    account_cols = st.columns(4)
    account_cols[0].metric("이메일", mask_email(account.get("email")))
    account_cols[1].metric("게임 계정 식별값", account.get("uid") or "-")
    account_cols[2].metric("서버 권역", account.get("server_region") or "-")
    account_cols[3].metric("계정 상태", account.get("account_status") or "-")

    if analyses:
        with st.expander("문의를 어떻게 분석했는지", expanded=True):
            render_data_table(analyses, kind="analysis")
    if drafts:
        with st.expander("작성된 초안", expanded=True):
            render_data_table(drafts, kind="history")
    if evidence_docs:
        with st.expander("답변에 붙인 근거", expanded=False):
            render_data_table(evidence_docs, kind="history")
    if safety_results:
        with st.expander("안전성 점검 결과", expanded=True):
            render_data_table(safety_results, kind="safety")
    if final_responses:
        with st.expander("실제로 보낸 답변", expanded=True):
            render_data_table(final_responses, kind="history")
    if notifications:
        with st.expander("보낸 알림", expanded=False):
            render_data_table(notifications, kind="failure_log")
    if voc_feedback:
        with st.expander("이용자 의견 기록", expanded=False):
            render_data_table(voc_feedback, kind="history")

    operation_payload = {
        "payments": operation_logs.get("payments", []),
        "refunds": operation_logs.get("refunds", []),
        "item_delivery_logs": operation_logs.get("item_delivery_logs", []),
        "gacha_logs": operation_logs.get("gacha_logs", []),
    }
    if any(operation_payload.values()):
        with st.expander("업무 처리 이력", expanded=False):
            for key, rows in operation_payload.items():
                if rows:
                    st.markdown(f"**{SECTION_LABELS.get(key, key)}**")
                    render_data_table(rows, kind="history")

    workflow_payload = {
        "admin_event_logs": workflow_logs.get("admin_event_logs", []),
        "failed_queries": workflow_logs.get("failed_queries", []),
    }
    if any(workflow_payload.values()):
        with st.expander("운영 처리 로그", expanded=False):
            for key, rows in workflow_payload.items():
                if rows:
                    st.markdown(f"**{SECTION_LABELS.get(key, key)}**")
                    render_data_table(rows, kind="history")


def render_weekly_report_section(
    report: dict[str, Any],
    *,
    pdf_bytes: bytes | None = None,
    default_pdf_name: str = "dashboard_weekly_report.pdf",
) -> None:
    window = report.get("window", {})
    summary = report.get("summary", {})
    comparisons = report.get("comparisons", {})

    render_ai_interpretation(report)
    st.caption(
        f"최근 {window.get('days', '-')}일 기준 주간 흐름입니다. "
        f"({window.get('window_start', '-')} ~ {window.get('window_end', '-')})"
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric("분석 건수", summary.get("analysis_count", 0), delta=comparisons.get("analysis_count", {}).get("change_rate"))
    metric_cols[1].metric("위험도가 높은 문의", summary.get("high_risk_count", 0), delta=comparisons.get("high_risk_count", {}).get("change_rate"))
    metric_cols[2].metric("부정 반응 문의", summary.get("negative_sentiment_count", 0), delta=comparisons.get("negative_sentiment_count", {}).get("change_rate"))
    metric_cols[3].metric("사람 확인이 필요한 문의", summary.get("human_review_count", 0), delta=comparisons.get("human_review_count", {}).get("change_rate"))

    left, right = st.columns(2, gap="large")
    with left:
        render_chart_box("문의가 어떤 종류였는지", as_bar_chart(report.get("category_distribution", [])))
        render_chart_box("위험도가 어떻게 나뉘는지", as_bar_chart(report.get("risk_distribution", [])))
        render_chart_box("누가 답변을 맡았는지", as_bar_chart(report.get("responder_distribution", [])))
    with right:
        render_chart_box("이용자 반응 분위기", as_bar_chart(report.get("sentiment_distribution", [])))
        render_chart_box("AI 응대 시도 & 담당자 즉시 알림", as_bar_chart(report.get("routing_distribution", [])))
        render_chart_box(
            "처리 단계별 진행 비율",
            as_bar_chart(
                [
                    {"label": "response_rate", "value": summary.get("response_rate", 0)},
                    {"label": "analysis_coverage", "value": summary.get("analysis_coverage_rate", 0)},
                    {"label": "draft_coverage", "value": summary.get("draft_coverage_rate", 0)},
                    {"label": "final_response", "value": summary.get("final_response_ticket_rate", 0)},
                ]
            ),
        )

    st.subheader("우선 확인이 필요한 문의")
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
                "ai_row_interpretation",
                "analyzed_at",
            ],
        ),
        kind="priority",
    )

    with st.expander("분석 원본을 전체로 보기", expanded=False):
        render_data_table(report.get("analysis_rows", []), kind="analysis")

    if pdf_bytes:
        st.download_button(
            "보고서 PDF 내려받기",
            data=pdf_bytes,
            file_name=default_pdf_name,
            mime="application/pdf",
            use_container_width=True,
        )
