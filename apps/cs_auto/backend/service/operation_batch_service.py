from __future__ import annotations

from datetime import date
from typing import Any

from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from common.db.connection import db_connection
from workflow.agents import run_context_agent, run_drafting_agent, run_intake_agent
from workflow.state import AnalysisResult, OperationState, SafetyResult, Ticket


class AnalysisStepResult(BaseModel):
    ticket_id: str
    ticket: Ticket
    query_text: str
    analysis: AnalysisResult
    metadata: dict[str, Any] = Field(default_factory=dict)
    analysis_id: int | None = None


class DraftStepResult(BaseModel):
    ticket_id: str
    ticket: Ticket
    query_text: str
    analysis: AnalysisResult
    analysis_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    context_nodes: list[str] = Field(default_factory=list)
    retrieved_docs: list[Any] = Field(default_factory=list)
    evidence_doc_ids: list[str] = Field(default_factory=list)
    answer_draft: str | None = None
    urgent_draft: str | None = None
    draft_id: int | None = None


_SAFETY_REASON_MAX_LENGTH = 255

# 리스트에서 개수 셀 때 함수를 변수명처럼 사용하기 위해 @property 사용
class BatchRunSummary(BaseModel):
    job_name: str
    processed_ticket_ids: list[int] = Field(default_factory=list)
    failed_ticket_ids: list[int] = Field(default_factory=list)
    skipped_ticket_ids: list[int] = Field(default_factory=list)

    @property
    def processed_count(self) -> int:
        return len(self.processed_ticket_ids)

    @property
    def failed_count(self) -> int:
        return len(self.failed_ticket_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_ticket_ids)


CONTEXT_NODE_BY_ROUTE = {
    "payment": "payment_context",
    "refund": "refund_context",
    "item_delivery": "item_delivery_context",
    "gacha": "gacha_context",
    "policy": "document_retrieval_context",
    "abuse": "document_retrieval_context",
    "outage": "document_retrieval_context",
}


def _fetch_ticket(ticket_id: str) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    t.ticket_id,
                    t.user_id,
                    t.account_id,
                    t.title,
                    t.raw_query,
                    t.source_type,
                    t.responder_type,
                    t.status,
                    t.inquiry_created_at,
                    t.session_id,
                    u.email,
                    u.nickname,
                    u.user_status,
                    a.game_name,
                    a.uid,
                    a.server_region,
                    a.progression_level,
                    a.account_status
                FROM qa_ticket t
                LEFT JOIN community_users u ON u.user_id = t.user_id
                LEFT JOIN game_accounts a ON a.account_id = t.account_id
                WHERE t.ticket_id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"qa_ticket not found: {ticket_id}")
            return dict(row)


def _ticket_from_row(row: dict[str, Any]) -> Ticket:
    return Ticket(
        ticket_id=str(row.get("ticket_id")),
        user_id=str(row.get("user_id")) if row.get("user_id") is not None else None,
        title=row.get("title"),
        body=row.get("raw_query"),
        channel=row.get("source_type"),
        responder_type=row.get("responder_type"),
        created_at=str(row.get("inquiry_created_at")) if row.get("inquiry_created_at") else None,
        metadata=row,
    )


def _payment_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT p.*
        FROM payments p
        JOIN game_accounts a ON a.account_id = p.account_id
        WHERE a.user_id = %s OR p.account_id = %s
        ORDER BY p.paid_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _refund_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT r.*, p.account_id, p.product_name, p.payment_status, p.paid_at
        FROM refunds r
        JOIN payments p ON p.payment_id = r.payment_id
        JOIN game_accounts a ON a.account_id = p.account_id
        WHERE a.user_id = %s OR p.account_id = %s
        ORDER BY r.requested_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _item_delivery_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT d.*
        FROM item_delivery_logs d
        JOIN game_accounts a ON a.account_id = d.account_id
        WHERE a.user_id = %s OR d.account_id = %s
        ORDER BY d.expected_at DESC NULLS LAST, d.delivered_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _gacha_rows(cur: Any, *, user_id: Any, account_id: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT g.*
        FROM gacha_logs g
        JOIN game_accounts a ON a.account_id = g.account_id
        WHERE a.user_id = %s OR g.account_id = %s
        ORDER BY g.pulled_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]



_DB_ROUTE_QUERY_FN = {
    "payment": _payment_rows,
    "refund": _refund_rows,
    "item_delivery": _item_delivery_rows,
    "gacha": _gacha_rows,
}


def _load_context_rows(route: str, ticket: Ticket) -> list[dict[str, Any]]:
    """Load only route-specific DB rows.

    Document evidence is retrieved separately from the full document corpus by
    ``workflow.agents.context._retrieve_docs``. Routes without a user/account DB
    table intentionally return an empty DB context.
    """

    user_id = ticket.user_id or ticket.metadata.get("user_id")
    account_id = ticket.metadata.get("account_id")
    ticket_id = str(ticket.ticket_id)
    query_fn = _DB_ROUTE_QUERY_FN.get(route)
    if query_fn is None:
        return []
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return query_fn(cur, user_id=user_id, account_id=account_id, ticket_id=ticket_id)


def _query_text(ticket: Ticket) -> str:
    query_text = ticket.body or ticket.title
    if not query_text:
        raise ValueError("ticket requires body or title")
    return query_text


def _safety_reason_text(reasons: list[str]) -> str:
    text = "\n".join(reason.strip() for reason in reasons if reason and reason.strip())
    if len(text) <= _SAFETY_REASON_MAX_LENGTH:
        return text
    return text[: _SAFETY_REASON_MAX_LENGTH - 3].rstrip() + "..."


def _insert_analysis(ticket: Ticket, query_text: str, analysis: AnalysisResult) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ticket_analysis (
                    ticket_id, category, responder_type, enriched_query,
                    risk_level, sentiment, routing_target, summary, analyzed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING analysis_id
                """,
                (
                    str(ticket.ticket_id),
                    analysis.query_route,
                    ticket.responder_type,
                    query_text,
                    analysis.risk_level,
                    None,
                    analysis.target_route,
                    analysis.summary,
                ),
            )
            return int(cur.fetchone()[0])


def _insert_draft(result: DraftStepResult, analysis_id: int) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO answer_draft (
                    ticket_id, analysis_id, draft_text, created_at
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING draft_id
                """,
                (
                    result.ticket_id,
                    analysis_id,
                    result.answer_draft or result.urgent_draft,
                ),
            )
            return int(cur.fetchone()[0])


def _insert_evidence_docs(result: DraftStepResult, draft_id: int) -> None:
    cited_ids = set(result.evidence_doc_ids)
    cited_docs = [doc for doc in result.retrieved_docs if getattr(doc, "doc_id", None) in cited_ids]
    if not cited_docs:
        return

    with db_connection() as conn:
        with conn.cursor() as cur:
            for rank, document in enumerate(cited_docs, start=1):
                cur.execute(
                    """
                    INSERT INTO evidence_docs (
                        draft_id, source_type, source_id,
                        evidence_text, relevance_score, retrieval_rank
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        draft_id,
                        document.source,
                        document.doc_id,
                        document.content,
                        document.score,
                        rank,
                    ),
                )


def _insert_safety_result(ticket_id: str, approval_route: str, safety_result: SafetyResult, retry_count: int = 0) -> int:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT draft_id
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"answer_draft not found for ticket_id={ticket_id}")
            draft_id = int(row["draft_id"])
            cur.execute(
                """
                INSERT INTO safety_results (
                    draft_id, hallucination_score, toxicity_score,
                    policy_violation_score, factuality_score, checked_at,
                    safety_action, safety_reason, retry_count
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                RETURNING safety_id
                """,
                (
                    draft_id,
                    1.0 if safety_result.hallucination_detected else 0.0,
                    1.0 if safety_result.unsafe_expression_detected else 0.0,
                    1.0 if safety_result.policy_violation_detected else 0.0,
                    1.0 if safety_result.evidence_matched else 0.0,
                    approval_route,
                    _safety_reason_text(safety_result.reasons),
                    retry_count,
                ),
            )
            return int(cur.fetchone()["safety_id"])


def _insert_final_response(ticket_id: str, draft_id: int, final_text: str, safety_action: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO final_response (
                    ticket_id, draft_id, final_text, safety_action, created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING response_id
                """,
                (ticket_id, draft_id, final_text, safety_action),
            )
            return int(cur.fetchone()[0])


def _insert_notification(ticket_id: str, message: str | None) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_logs (
                    ticket_id, channel, status, message, sent_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING notification_id
                """,
                (ticket_id, "operation", "pending", message),
            )
            return int(cur.fetchone()[0])


def _update_ticket_status(ticket_id: str, status: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                (status, ticket_id),
            )


def _load_draft_row(draft_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT draft_id, ticket_id, analysis_id, draft_text, created_at
                FROM answer_draft
                WHERE draft_id = %s
                """,
                (draft_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"answer_draft not found: {draft_id}")
            return dict(row)


def _latest_draft_id(ticket_id: str) -> int:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT draft_id
                FROM answer_draft
                WHERE ticket_id = %s
                ORDER BY created_at DESC NULLS LAST, draft_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"answer_draft not found for ticket_id={ticket_id}")
            return int(row["draft_id"])


def _update_draft_text(draft_id: int, draft_text: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE answer_draft
                SET draft_text = %s
                WHERE draft_id = %s
                """,
                (draft_text, draft_id),
            )


def _load_latest_analysis_row(ticket_id: str) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    analysis_id,
                    ticket_id,
                    category,
                    responder_type,
                    enriched_query,
                    risk_level,
                    sentiment,
                    routing_target,
                    summary,
                    analyzed_at
                FROM ticket_analysis
                WHERE ticket_id = %s
                ORDER BY analyzed_at DESC NULLS LAST, analysis_id DESC
                LIMIT 1
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"ticket_analysis not found for ticket_id={ticket_id}")
            return dict(row)


def load_ticket_payload(ticket_id: int | str) -> Ticket:
    row = _fetch_ticket(str(ticket_id))
    return _ticket_from_row(row)


def load_latest_analysis_result(ticket_id: int | str) -> AnalysisStepResult:
    ticket = load_ticket_payload(ticket_id)
    row = _load_latest_analysis_row(str(ticket_id))
    analysis = AnalysisResult(
        query_route=row.get("category"),
        target_route=row.get("routing_target"),
        risk_level=row.get("risk_level"),
        risk_reason=None,
        summary=row.get("summary"),
        required_actions=[],
    )
    return AnalysisStepResult(
        ticket_id=str(ticket.ticket_id),
        ticket=ticket,
        query_text=row.get("enriched_query") or _query_text(ticket),
        analysis=analysis,
        metadata={
            "source": "latest_ticket_analysis",
            "analyzed_at": str(row.get("analyzed_at")) if row.get("analyzed_at") else None,
        },
        analysis_id=int(row["analysis_id"]),
    )


def classify_ticket(ticket: Ticket) -> AnalysisStepResult:
    query_text = _query_text(ticket)
    state = OperationState(ticket_id=str(ticket.ticket_id), ticket=ticket, query_text=query_text)
    response = run_intake_agent(state)
    analysis = AnalysisResult(
        query_route=response.query_route,
        target_route=response.target_route,
        risk_level=response.risk_level,
        risk_reason=response.risk_reason,
        summary=response.summary,
        required_actions=response.required_actions,
    )
    return AnalysisStepResult(
        ticket_id=str(ticket.ticket_id),
        ticket=ticket,
        query_text=query_text,
        analysis=analysis,
        metadata={
            "review_required": response.review_required,
            "review_reason": response.review_reason,
            "required_context_types": response.required_context_types,
            "route_reason": response.route_reason,
        },
    )


def persist_analysis_result(result: AnalysisStepResult) -> int:
    analysis_id = _insert_analysis(result.ticket, result.query_text, result.analysis)
    result.analysis_id = analysis_id
    return analysis_id


def build_draft_inputs(ticket: Ticket, analysis_result: AnalysisStepResult, *, regeneration_reason: str | None = None) -> DraftStepResult:
    route = analysis_result.analysis.query_route
    target_route = analysis_result.analysis.target_route
    if route is None or target_route is None:
        raise ValueError("analysis_result requires query_route and target_route")

    context_rows = _load_context_rows(route, ticket)
    state = OperationState(
        ticket_id=str(ticket.ticket_id),
        ticket=ticket,
        query_text=analysis_result.query_text,
        query_route=route,
        target_route=target_route,
        analysis=analysis_result.analysis,
        metadata=analysis_result.metadata,
        regeneration_reason=regeneration_reason,
    )
    context_node_name = CONTEXT_NODE_BY_ROUTE.get(route)
    if context_node_name is None:
        raise ValueError(f"unsupported query_route for draft: {route!r}")
    context_result = run_context_agent(
        state=state,
        route=route,
        target_route=target_route,
        context_rows=context_rows,
        context_node_name=context_node_name,
    )
    state = state.model_copy(
        update={
            "context": context_result.context,
            "context_nodes": context_result.context_nodes,
            "retrieved_docs": context_result.retrieved_docs,
            "evidence_doc_ids": context_result.evidence_doc_ids,
            "errors": context_result.errors,
        }
    )
    draft_response = run_drafting_agent(state)
    valid_ids = {doc.doc_id for doc in context_result.retrieved_docs if doc.doc_id}
    filtered_ids = [doc_id for doc_id in draft_response.evidence_doc_ids if doc_id in valid_ids]
    if not filtered_ids:
        filtered_ids = [doc_id for doc_id in context_result.evidence_doc_ids[:3] if doc_id in valid_ids]

    return DraftStepResult(
        ticket_id=str(ticket.ticket_id),
        ticket=ticket,
        query_text=analysis_result.query_text,
        analysis=analysis_result.analysis,
        analysis_id=analysis_result.analysis_id,
        metadata=analysis_result.metadata
        | {
            "review_required": draft_response.review_required,
            "review_reason": draft_response.review_reason,
            "operator_handoff_answer": draft_response.operator_handoff_answer,
        },
        context=context_result.context,
        context_nodes=context_result.context_nodes,
        retrieved_docs=context_result.retrieved_docs,
        evidence_doc_ids=filtered_ids,
        answer_draft=draft_response.customer_answer.strip() if draft_response.customer_answer else None,
        urgent_draft=draft_response.urgent_alert_message.strip() if draft_response.urgent_alert_message else None,
    )


def persist_draft_result(result: DraftStepResult, analysis_id: int) -> int:
    draft_id = _insert_draft(result, analysis_id)
    _insert_evidence_docs(result, draft_id)
    source_type = result.ticket.channel or result.ticket.metadata.get("source_type")
    current_status = result.ticket.metadata.get("status")
    if not (source_type == "naver_cafe" and current_status == "open"):
        _update_ticket_status(result.ticket_id, "pending")
    result.draft_id = draft_id
    return draft_id


def run_analysis_step(ticket_id: int | str, *, persist: bool = True) -> AnalysisStepResult:
    ticket = load_ticket_payload(ticket_id)
    result = classify_ticket(ticket)
    if persist:
        persist_analysis_result(result)
    return result


def run_draft_step(ticket_id: int | str, *, persist_analysis: bool = True, persist_draft: bool = True, regeneration_reason: str | None = None) -> DraftStepResult:
    ticket = load_ticket_payload(ticket_id)
    analysis_result = classify_ticket(ticket)
    if persist_analysis:
        persist_analysis_result(analysis_result)
    result = build_draft_inputs(ticket, analysis_result, regeneration_reason=regeneration_reason)
    if persist_draft and analysis_result.analysis_id is not None:
        persist_draft_result(result, analysis_result.analysis_id)
    return result


def run_draft_step_from_latest_analysis(ticket_id: int | str, *, persist_draft: bool = True, regeneration_reason: str | None = None) -> DraftStepResult:
    analysis_result = load_latest_analysis_result(ticket_id)
    result = build_draft_inputs(analysis_result.ticket, analysis_result, regeneration_reason=regeneration_reason)
    if persist_draft and analysis_result.analysis_id is not None:
        persist_draft_result(result, analysis_result.analysis_id)
    return result


def list_analysis_candidate_ticket_ids(*, limit: int = 200, target_date: date | None = None) -> list[int]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if target_date is None:
                cur.execute(
                    """
                    SELECT t.ticket_id
                    FROM qa_ticket t
                    LEFT JOIN LATERAL (
                        SELECT analysis_id
                        FROM ticket_analysis a
                        WHERE a.ticket_id = t.ticket_id
                        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                        LIMIT 1
                    ) latest_analysis ON TRUE
                    WHERE (
                        (t.source_type = 'chatbot' AND t.status IN ('pending', 'resolved'))
                        OR (t.source_type = 'naver_cafe' AND t.status IN ('open', 'pending'))
                    )
                      AND latest_analysis.analysis_id IS NULL
                    ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cur.execute(
                    """
                    SELECT t.ticket_id
                    FROM qa_ticket t
                    LEFT JOIN LATERAL (
                        SELECT analysis_id
                        FROM ticket_analysis a
                        WHERE a.ticket_id = t.ticket_id
                        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                        LIMIT 1
                    ) latest_analysis ON TRUE
                    WHERE (
                        (t.source_type = 'chatbot' AND t.status IN ('pending', 'resolved'))
                        OR (t.source_type = 'naver_cafe' AND t.status IN ('open', 'pending'))
                    )
                      AND latest_analysis.analysis_id IS NULL
                      AND t.inquiry_created_at >= %s
                      AND t.inquiry_created_at < %s::date + INTERVAL '1 day'
                    ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                    LIMIT %s
                    """,
                    (target_date, target_date, limit),
                )
            return [int(row["ticket_id"]) for row in cur.fetchall()]


def list_naver_cafe_draft_candidate_ticket_ids(*, limit: int = 200, target_date: date | None = None) -> list[int]:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            params: list[Any]
            if target_date is None:
                query = """
                    SELECT t.ticket_id
                    FROM qa_ticket t
                    JOIN LATERAL (
                        SELECT analysis_id
                        FROM ticket_analysis a
                        WHERE a.ticket_id = t.ticket_id
                        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                        LIMIT 1
                    ) latest_analysis ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT draft_id
                        FROM answer_draft d
                        WHERE d.ticket_id = t.ticket_id
                        ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
                        LIMIT 1
                    ) latest_draft ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT response_id
                        FROM final_response f
                        WHERE f.ticket_id = t.ticket_id
                        ORDER BY f.created_at DESC NULLS LAST, f.response_id DESC
                        LIMIT 1
                    ) latest_response ON TRUE
                    WHERE t.status = 'open'
                      AND t.source_type = 'naver_cafe'
                      AND latest_draft.draft_id IS NULL
                      AND latest_response.response_id IS NULL
                    ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                    LIMIT %s
                """
                params = [limit]
            else:
                query = """
                    SELECT t.ticket_id
                    FROM qa_ticket t
                    JOIN LATERAL (
                        SELECT analysis_id
                        FROM ticket_analysis a
                        WHERE a.ticket_id = t.ticket_id
                        ORDER BY a.analyzed_at DESC NULLS LAST, a.analysis_id DESC
                        LIMIT 1
                    ) latest_analysis ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT draft_id
                        FROM answer_draft d
                        WHERE d.ticket_id = t.ticket_id
                        ORDER BY d.created_at DESC NULLS LAST, d.draft_id DESC
                        LIMIT 1
                    ) latest_draft ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT response_id
                        FROM final_response f
                        WHERE f.ticket_id = t.ticket_id
                        ORDER BY f.created_at DESC NULLS LAST, f.response_id DESC
                        LIMIT 1
                    ) latest_response ON TRUE
                    WHERE t.status = 'open'
                      AND t.source_type = 'naver_cafe'
                      AND latest_draft.draft_id IS NULL
                      AND latest_response.response_id IS NULL
                      AND t.inquiry_created_at >= %s
                      AND t.inquiry_created_at < %s::date + INTERVAL '1 day'
                    ORDER BY t.inquiry_created_at ASC NULLS LAST, t.ticket_id ASC
                    LIMIT %s
                """
                params = [target_date, target_date, limit]
            cur.execute(query, tuple(params))
            return [int(row["ticket_id"]) for row in cur.fetchall()]


def _is_analysis_candidate(ticket_id: int) -> bool:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT source_type, status
                FROM qa_ticket
                WHERE ticket_id = %s
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            source_type = row["source_type"]
            status = row["status"]
            if source_type == "chatbot" and status in ("pending", "resolved"):
                return True
            if source_type == "naver_cafe" and status in ("open", "pending"):
                return True
            return False


def run_scheduled_analysis_batch(*, limit: int = 200, target_date: date | None = None) -> BatchRunSummary:
    summary = BatchRunSummary(job_name="scheduled_analysis_batch")
    for ticket_id in list_analysis_candidate_ticket_ids(limit=limit, target_date=target_date):
        if not _is_analysis_candidate(ticket_id):
            summary.skipped_ticket_ids.append(ticket_id)
            continue
        try:
            run_analysis_step(ticket_id, persist=True)
            summary.processed_ticket_ids.append(ticket_id)
        except Exception:
            summary.failed_ticket_ids.append(ticket_id)
    return summary


def run_scheduled_naver_cafe_draft_batch(*, limit: int = 200, target_date: date | None = None) -> BatchRunSummary:
    summary = BatchRunSummary(job_name="scheduled_naver_cafe_draft_batch")
    for ticket_id in list_naver_cafe_draft_candidate_ticket_ids(limit=limit, target_date=target_date):
        try:
            run_draft_step_from_latest_analysis(ticket_id, persist_draft=True)
            summary.processed_ticket_ids.append(ticket_id)
        except LookupError:
            summary.skipped_ticket_ids.append(ticket_id)
        except Exception:
            summary.failed_ticket_ids.append(ticket_id)
    return summary
