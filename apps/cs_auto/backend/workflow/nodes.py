"""Compatibility node wrappers for the deprecated cs_auto workflow graph.

The active execution path now lives in ``service.operation_batch_service``.
This module remains only as a thin compatibility surface for older tests,
docs, and callers that still expect graph-style node functions.
"""

from __future__ import annotations

from typing import Any, Callable

from common.llm.client import invoke_structured_llm
from common.db.connection import db_connection
from service import operation_batch_service as batch
from workflow.agents import run_context_agent, run_drafting_agent, run_intake_agent, run_review_agent
from workflow.prompts import HUMAN_REVIEW_PROMPT, HUMAN_REVIEW_SYSTEM_PROMPT, HumanReviewResponse, SYSTEM_PROMPT, render_state
from workflow.state import AnalysisResult, HumanDecision, HumanReviewResult, OperationState, SafetyResult, Ticket


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[OperationState], StateUpdate]


def _state(state: OperationState | dict[str, Any]) -> OperationState:
    return OperationState.model_validate(state)


def _ticket_key(state: OperationState) -> str:
    ticket_id = state.ticket_id or state.ticket.ticket_id
    if not ticket_id:
        raise ValueError("operation workflow requires ticket_id")
    return str(ticket_id)


def _fetch_ticket(ticket_id: str) -> dict[str, Any]:
    batch.db_connection = db_connection
    return batch._fetch_ticket(ticket_id)


def _context_for_route(route: str, state: OperationState) -> list[dict[str, Any]]:
    batch.db_connection = db_connection
    return batch._load_context_rows(route, state.ticket)


def _insert_analysis(state: OperationState) -> int:
    batch.db_connection = db_connection
    return batch._insert_analysis(state.ticket, state.query_text or state.ticket.body or state.ticket.title or "", state.analysis)


def _insert_draft(state: OperationState, analysis_id: int) -> int:
    batch.db_connection = db_connection
    result = batch.DraftStepResult(
        ticket_id=_ticket_key(state),
        ticket=state.ticket,
        query_text=state.query_text or state.ticket.body or state.ticket.title or "",
        analysis=state.analysis,
        metadata=state.metadata,
        context=state.context,
        context_nodes=state.context_nodes,
        retrieved_docs=state.retrieved_docs,
        evidence_doc_ids=state.evidence_doc_ids,
        answer_draft=state.answer_draft,
        urgent_draft=state.urgent_draft,
    )
    return batch._insert_draft(result, analysis_id)


def _insert_evidence_docs(state: OperationState, draft_id: int) -> None:
    batch.db_connection = db_connection
    result = batch.DraftStepResult(
        ticket_id=_ticket_key(state),
        ticket=state.ticket,
        query_text=state.query_text or state.ticket.body or state.ticket.title or "",
        analysis=state.analysis,
        metadata=state.metadata,
        context=state.context,
        context_nodes=state.context_nodes,
        retrieved_docs=state.retrieved_docs,
        evidence_doc_ids=state.evidence_doc_ids,
        answer_draft=state.answer_draft,
        urgent_draft=state.urgent_draft,
    )
    batch._insert_evidence_docs(result, draft_id)


def _insert_safety_result(state: OperationState, draft_id: int) -> int:
    batch.db_connection = db_connection
    review_result = batch.ReviewStepResult(
        ticket_id=_ticket_key(state),
        approval_route=state.approval_route or "human_review",
        safety_result=state.safety_result,
    )
    return batch._insert_safety_result(review_result.ticket_id, review_result.approval_route, review_result.safety_result, retry_count=state.retry_count or 0)


def _insert_final_response(state: OperationState, draft_id: int) -> int:
    batch.db_connection = db_connection
    final_answer = state.edited_answer or state.answer_draft or state.urgent_draft
    if not final_answer:
        raise ValueError("finalize requires final answer text for approved route")
    return batch._insert_final_response(_ticket_key(state), draft_id, final_answer, state.approval_route or "approved")


def _insert_notification(state: OperationState) -> int:
    batch.db_connection = db_connection
    return batch._insert_notification(_ticket_key(state), state.urgent_draft or state.answer_draft)


def _update_ticket_status(ticket_id: str, status: str) -> None:
    batch.db_connection = db_connection
    batch._update_ticket_status(ticket_id, status)


def load_ticket(state: OperationState) -> StateUpdate:
    current = _state(state)
    row = _fetch_ticket(_ticket_key(current))
    ticket = Ticket(
        ticket_id=str(row.get("ticket_id")),
        user_id=str(row.get("user_id")) if row.get("user_id") is not None else None,
        title=row.get("title"),
        body=row.get("raw_query"),
        channel=row.get("source_type"),
        responder_type=row.get("responder_type"),
        created_at=str(row.get("inquiry_created_at")) if row.get("inquiry_created_at") else None,
        metadata=row,
    )
    return {"ticket": ticket, "query_text": ticket.body, "status": row.get("status")}


def intake_agent(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = run_intake_agent(current)
    analysis = AnalysisResult(
        query_route=response.query_route,
        target_route=response.target_route,
        risk_level=response.risk_level,
        risk_reason=response.risk_reason,
        summary=response.summary,
        required_actions=response.required_actions,
    )
    return {
        "query_route": response.query_route,
        "query_route_reason": response.route_reason,
        "target_route": response.target_route,
        "analysis": analysis,
        "metadata": current.metadata
        | {
            "review_required": response.review_required,
            "review_reason": response.review_reason,
            "required_context_types": response.required_context_types,
        },
    }


def context_agent(state: OperationState) -> StateUpdate:
    current = _state(state)
    route = current.query_route or current.analysis.query_route
    if route is None:
        raise ValueError("context_agent requires query_route")
    target_route = current.target_route or current.analysis.target_route
    if target_route is None:
        raise ValueError("context_agent requires target_route")
    rows = _context_for_route(route, current)
    result = run_context_agent(
        state=current,
        route=route,
        target_route=target_route,
        context_rows=rows,
        context_node_name=batch.CONTEXT_NODE_BY_ROUTE[route],
    )
    return result.model_dump()


def drafting_agent(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = run_drafting_agent(current)
    answer_draft = response.customer_answer.strip() if response.customer_answer else None
    urgent_draft = response.urgent_alert_message.strip() if response.urgent_alert_message else None
    operator_handoff = response.operator_handoff_answer.strip() if response.operator_handoff_answer else None
    valid_ids = {doc.doc_id for doc in current.retrieved_docs if doc.doc_id}
    filtered_ids = [doc_id for doc_id in response.evidence_doc_ids if doc_id in valid_ids][:3]
    return {
        "answer_draft": answer_draft,
        "urgent_draft": urgent_draft,
        "evidence_doc_ids": filtered_ids,
        "metadata": current.metadata
        | {
            "review_required": response.review_required,
            "review_reason": response.review_reason,
            "operator_handoff_answer": operator_handoff,
        },
    }


def review_agent(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = run_review_agent(current)
    return {
        "approval_route": response.approval_route,
        "safety_result": SafetyResult(
            approved=response.approved,
            evidence_matched=response.evidence_matched,
            hallucination_detected=response.hallucination_detected,
            policy_violation_detected=response.policy_violation_detected,
            unsafe_expression_detected=response.unsafe_expression_detected,
            reasons=response.reasons,
        ),
    }


def review(state: OperationState) -> StateUpdate:
    current = _state(state)
    if current.human_review.decision or current.human_decision:
        decision = current.human_review.decision or current.human_decision
        reason = current.human_review.reason or current.metadata.get("review_reason") or "manual review input"
        edited_answer = current.human_review.edited_answer or current.edited_answer
        response = HumanReviewResponse(
            decision=decision,  # type: ignore[arg-type]
            reason=str(reason),
            edited_answer=edited_answer,
        )
    else:
        response = invoke_structured_llm(
            system_prompt=HUMAN_REVIEW_SYSTEM_PROMPT or SYSTEM_PROMPT,
            user_prompt=HUMAN_REVIEW_PROMPT.format(state_json=render_state(current)),
            response_model=HumanReviewResponse,
        )

    human_review = HumanReviewResult(
        decision=response.decision,
        reason=response.reason,
        edited_answer=response.edited_answer,
    )
    update: dict[str, Any] = {
        "human_decision": response.decision,
        "human_review": human_review,
        "edited_answer": response.edited_answer,
    }
    if response.decision == "regenerate":
        update |= {
            "metadata": current.metadata | {"regenerate_reason": response.reason},
            "answer_draft": None,
            "urgent_draft": None,
            "evidence_doc_ids": [],
            "retrieved_docs": [],
            "approval_route": None,
            "safety_result": SafetyResult(),
            "edited_answer": None,
        }
    return update


def finalize(state: OperationState) -> StateUpdate:
    current = _state(state)
    ticket_id = _ticket_key(current)
    analysis_id = _insert_analysis(current)
    draft_id = _insert_draft(current, analysis_id)
    _insert_evidence_docs(current, draft_id)
    safety_id = _insert_safety_result(current, draft_id)

    update: dict[str, Any] = {
        "analysis_id": analysis_id,
        "draft_id": draft_id,
        "safety_id": safety_id,
    }

    effective_route = current.approval_route
    if current.human_decision in {"approved", "edit"} and effective_route == "human_review":
        effective_route = "approved"

    if effective_route == "approved":
        response_id = _insert_final_response(current, draft_id)
        _update_ticket_status(ticket_id, "closed")
        update |= {
            "response_id": response_id,
            "final_answer": current.edited_answer or current.answer_draft or current.urgent_draft,
            "status": "closed",
        }
        return update

    if effective_route == "urgent_alert":
        notification_id = _insert_notification(current)
        _update_ticket_status(ticket_id, "urgent_alert_pending")
        update |= {"notification_id": notification_id, "status": "urgent_alert_pending"}
        return update

    _update_ticket_status(ticket_id, "pending")
    update |= {"status": "pending"}
    return update


NODE_FUNCTIONS: dict[str, NodeHandler] = {
    "load_ticket": load_ticket,
    "intake_agent": intake_agent,
    "context_agent": context_agent,
    "drafting_agent": drafting_agent,
    "review_agent": review_agent,
    "review": review,
    "finalize": finalize,
}
