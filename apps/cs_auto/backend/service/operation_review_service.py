from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from pydantic import BaseModel

from common.db.connection import db_connection
from workflow.agents import run_review_agent
from workflow.state import OperationState, SafetyResult

from .operation_batch_service import DraftStepResult, _latest_draft_id, run_draft_step


class ReviewStepResult(BaseModel):
    ticket_id: str
    approval_route: str
    safety_result: SafetyResult
    safety_id: int | None = None
    response_id: int | None = None
    final_answer: str | None = None
    status: str | None = None


_TERMINAL_TICKET_STATUSES = {"closed", "resolved", "urgent_alert_pending"}
_ACTIVE_WORKFLOW_STATUS = "workflow_running"
_SAFETY_REASON_MAX_LENGTH = 255


# _load_draft_row ?? ??
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


# _update_draft_text ?? ??
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


# _insert_final_response ?? ??
def _insert_final_response(ticket_id: str, draft_id: int, final_text: str, safety_action: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO final_response (
                    ticket_id, draft_id, final_text, safety_action, created_at
                )
                SELECT %s, %s, %s, %s, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM final_response
                    WHERE draft_id = %s
                )
                RETURNING response_id
                """,
                (ticket_id, draft_id, final_text, safety_action, draft_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"final_response already exists for draft_id={draft_id}")
            return int(row[0])

"""
notification logs가 뭐하는 DB더라....
"""
# _insert_notification ?? ??
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


# _update_ticket_status ?? ??
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


# _safety_reason_text ?? ??
def _safety_reason_text(reasons: list[str]) -> str:
    text = "\n".join(reason.strip() for reason in reasons if reason and reason.strip())
    if len(text) <= _SAFETY_REASON_MAX_LENGTH:
        return text
    return text[: _SAFETY_REASON_MAX_LENGTH - 3].rstrip() + "..."


# _begin_ticket_workflow ?? ??
def _begin_ticket_workflow(ticket_id: str) -> str:
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT status
                FROM qa_ticket
                WHERE ticket_id = %s
                FOR UPDATE
                """,
                (ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"qa_ticket not found: {ticket_id}")

            current_status = str(row["status"])
            if current_status in _TERMINAL_TICKET_STATUSES:
                raise ValueError(f"ticket {ticket_id} is already terminal: {current_status}")
            if current_status == _ACTIVE_WORKFLOW_STATUS:
                raise ValueError(f"ticket {ticket_id} workflow is already running")

            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                (_ACTIVE_WORKFLOW_STATUS, ticket_id),
            )
            return current_status


# review_draft_result ?? ??
def review_draft_result(result: DraftStepResult) -> ReviewStepResult:
    state = OperationState(
        ticket_id=result.ticket_id,
        ticket=result.ticket,
        query_text=result.query_text,
        query_route=result.analysis.query_route,
        target_route=result.analysis.target_route,
        analysis=result.analysis,
        metadata=result.metadata,
        context=result.context,
        context_nodes=result.context_nodes,
        retrieved_docs=result.retrieved_docs,
        evidence_doc_ids=result.evidence_doc_ids,
        answer_draft=result.answer_draft,
        urgent_draft=result.urgent_draft,
    )
    response = run_review_agent(state)
    return ReviewStepResult(
        ticket_id=result.ticket_id,
        approval_route=response.approval_route,
        safety_result=SafetyResult(
            approved=response.approved,
            evidence_matched=response.evidence_matched,
            hallucination_detected=response.hallucination_detected,
            policy_violation_detected=response.policy_violation_detected,
            unsafe_expression_detected=response.unsafe_expression_detected,
            reasons=response.reasons,
        ),
    )


# persist_review_result ?? ??
def persist_review_result(result: ReviewStepResult, retry_count: int = 0) -> int:
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
                (result.ticket_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"answer_draft not found for ticket_id={result.ticket_id}")
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
                    1.0 if result.safety_result.hallucination_detected else 0.0,
                    1.0 if result.safety_result.unsafe_expression_detected else 0.0,
                    1.0 if result.safety_result.policy_violation_detected else 0.0,
                    1.0 if result.safety_result.evidence_matched else 0.0,
                    result.approval_route,
                    _safety_reason_text(result.safety_result.reasons),
                    retry_count,
                ),
            )
            safety_id = int(cur.fetchone()["safety_id"])
            result.safety_id = safety_id
            return safety_id


# finalize_review_result ?? ??
def finalize_review_result(
    review_result: ReviewStepResult,
    *,
    draft_id: int,
    final_answer: str | None,
    notification_message: str | None = None,
) -> ReviewStepResult:
    effective_answer = final_answer or notification_message
    if review_result.approval_route == "approved":
        if not effective_answer:
            raise ValueError("approved review result requires final_answer")
        response_id = _insert_final_response(review_result.ticket_id, draft_id, effective_answer, review_result.approval_route)
        _update_ticket_status(review_result.ticket_id, "resolved")
        review_result.response_id = response_id
        review_result.final_answer = effective_answer
        review_result.status = "resolved"
        return review_result

    if review_result.approval_route == "urgent_alert":
        _insert_notification(review_result.ticket_id, notification_message)
        _update_ticket_status(review_result.ticket_id, "urgent_alert_pending")
        review_result.status = "urgent_alert_pending"
        return review_result

    _update_ticket_status(review_result.ticket_id, "pending")
    review_result.status = "pending"
    return review_result


# run_review_step ?? ??
def run_review_step(
    ticket_id: int | str,
    *,
    persist_analysis: bool = True,
    persist_draft: bool = True,
    persist_review: bool = True,
) -> ReviewStepResult:
    draft_result = run_draft_step(ticket_id, persist_analysis=persist_analysis, persist_draft=persist_draft)
    result = review_draft_result(draft_result)
    if persist_review:
        persist_review_result(result)
    return result


# run_workflow_step ?? ??
def run_workflow_step(ticket_id: int | str, *, regeneration_reason: str | None = None) -> dict[str, Any]:
    normalized_ticket_id = str(ticket_id)
    previous_status = _begin_ticket_workflow(normalized_ticket_id)
    try:
        draft_result = run_draft_step(normalized_ticket_id, persist_analysis=True, persist_draft=True, regeneration_reason=regeneration_reason)
        review_result = review_draft_result(draft_result)
        persist_review_result(review_result)
        finalized = finalize_review_result(
            review_result,
            draft_id=draft_result.draft_id or _latest_draft_id(draft_result.ticket_id),
            final_answer=draft_result.answer_draft,
            notification_message=draft_result.urgent_draft or draft_result.answer_draft,
        )
        analysis_id = draft_result.analysis_id if draft_result.analysis_id is not None else None
        return {
            "ticket_id": int(draft_result.ticket_id),
            "status": finalized.status or "unknown",
            "final_answer": finalized.final_answer,
            "draft_id": draft_result.draft_id,
            "analysis_id": analysis_id,
            "response_id": finalized.response_id,
        }
    except Exception:
        _update_ticket_status(normalized_ticket_id, previous_status)
        raise


# edit_existing_draft ?? ??
def edit_existing_draft(draft_id: int, draft_text: str) -> dict[str, Any]:
    draft = _load_draft_row(draft_id)
    _update_draft_text(draft_id, draft_text)
    _update_ticket_status(str(draft["ticket_id"]), "pending")
    return {
        "ticket_id": int(draft["ticket_id"]),
        "draft_id": draft_id,
        "status": "pending",
        "response_id": None,
        "next_draft_id": draft_id,
    }


# approve_existing_draft ?? ??
def approve_existing_draft(draft_id: int, final_text: str | None = None) -> dict[str, Any]:
    draft = _load_draft_row(draft_id)
    final_answer = final_text or draft.get("draft_text")
    if not final_answer:
        raise ValueError("approve_existing_draft requires final_text or stored draft_text")
    response_id = _insert_final_response(str(draft["ticket_id"]), draft_id, str(final_answer), "approved")
    _update_ticket_status(str(draft["ticket_id"]), "resolved")
    return {
        "ticket_id": int(draft["ticket_id"]),
        "draft_id": draft_id,
        "status": "resolved",
        "response_id": response_id,
        "next_draft_id": draft_id,
    }


# regenerate_from_draft ?? ??
def regenerate_from_draft(draft_id: int, *, reason: str | None = None) -> dict[str, Any]:
    draft = _load_draft_row(draft_id)
    result = run_workflow_step(int(draft["ticket_id"]), regeneration_reason=reason)
    return {
        "ticket_id": int(draft["ticket_id"]),
        "draft_id": draft_id,
        "status": result["status"],
        "response_id": result.get("response_id"),
        "next_draft_id": result.get("draft_id"),
    }
