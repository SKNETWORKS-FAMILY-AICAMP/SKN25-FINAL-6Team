"""Active nodes for the 6-step operation workflow."""

from __future__ import annotations

import logging
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, cast

from psycopg.rows import dict_row

from common.db.connection import db_connection
from common.llm.client import invoke_structured_llm

from .agents import run_context_agent, run_drafting_agent, run_intake_agent, run_review_agent
from .prompts import HUMAN_REVIEW_PROMPT, HUMAN_REVIEW_SYSTEM_PROMPT, HumanReviewResponse, SYSTEM_PROMPT, render_state
from .state import AnalysisResult, HumanReviewResult, HumanDecision, OperationState, QueryRoute, SafetyResult, TargetRoute, Ticket


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[OperationState], StateUpdate]

LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "operation"
LOG_FILE = LOG_DIR / "workflow.log"

CONTEXT_NODE_BY_ROUTE: dict[QueryRoute, str] = {
    "payment": "payment_context",
    "refund": "refund_context",
    "item_delivery": "item_delivery_context",
    "gacha": "gacha_context",
    "policy": "policy_context",
    "abuse": "abuse_context",
    "outage": "outage_context",
}


def _operation_logger() -> logging.Logger:
    logger = logging.getLogger("operation.workflow")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def _state_log_fields(state: OperationState) -> dict[str, Any]:
    return {
        "ticket_id": state.ticket_id or state.ticket.ticket_id,
        "query_route": state.query_route,
        "target_route": state.target_route or state.analysis.target_route,
        "approval_route": state.approval_route,
        "analysis_id": state.analysis_id,
        "draft_id": state.draft_id,
        "safety_id": state.safety_id,
        "response_id": state.response_id,
        "status": state.status,
    }


def _update_log_fields(update: StateUpdate) -> dict[str, Any]:
    if not update:
        return {}
    tracked = {
        "query_route",
        "target_route",
        "approval_route",
        "analysis_id",
        "draft_id",
        "safety_id",
        "response_id",
        "notification_id",
        "status",
    }
    return {key: update[key] for key in tracked if key in update}


def _with_node_logging(node_name: str, handler: NodeHandler) -> NodeHandler:
    @wraps(handler)
    def wrapped(state: OperationState) -> StateUpdate:
        logger = _operation_logger()
        current = _state(state)
        started_at = perf_counter()
        logger.info("node_start name=%s state=%s", node_name, _state_log_fields(current))
        try:
            update = handler(current)
        except Exception:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception("node_error name=%s elapsed_ms=%s state=%s", node_name, elapsed_ms, _state_log_fields(current))
            raise
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info("node_end name=%s elapsed_ms=%s update=%s", node_name, elapsed_ms, _update_log_fields(update))
        return update

    return wrapped


def _state(state: OperationState | dict[str, Any]) -> OperationState:
    return OperationState.model_validate(state)


def _ticket_key(state: OperationState) -> str:
    ticket_id = state.ticket_id or state.ticket.ticket_id
    if not ticket_id:
        raise ValueError("operation workflow requires ticket_id")
    return str(ticket_id)


def _query_text(state: OperationState) -> str:
    query_text = state.query_text or state.ticket.body or state.ticket.title
    if not query_text:
        raise ValueError("operation workflow requires query_text or ticket body")
    return query_text


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


def _abuse_rows(cur: Any, *, user_id: Any, account_id: Any, ticket_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT i.*, v.voc_type, v.sentiment AS voc_sentiment, v.topic_keywords
        FROM insight i
        LEFT JOIN voc_feedback v ON v.ticket_id = i.ticket_id
        WHERE i.user_id = %s OR i.ticket_id = %s OR i.account_id = %s
        ORDER BY i.inquiry_created_at DESC NULLS LAST
        LIMIT 10
        """,
        (user_id, ticket_id, account_id),
    )
    return [dict(row) for row in cur.fetchall()]


def _outage_rows(cur: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT documents_id, source_type, category, title, raw_content, source_url, published_at, updated_at
        FROM documents
        WHERE category ILIKE %s OR title ILIKE %s OR raw_content ILIKE %s
        ORDER BY updated_at DESC NULLS LAST, published_at DESC NULLS LAST
        LIMIT 10
        """,
        ("%outage%", "%outage%", "%outage%"),
    )
    return [dict(row) for row in cur.fetchall()]


def _policy_rows(cur: Any, **_: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT documents_id, source_type, category, title, raw_content, source_url, published_at, updated_at
        FROM documents
        WHERE category ILIKE %s OR title ILIKE %s OR raw_content ILIKE %s
        ORDER BY updated_at DESC NULLS LAST, published_at DESC NULLS LAST
        LIMIT 10
        """,
        ("%policy%", "%policy%", "%policy%"),
    )
    return [dict(row) for row in cur.fetchall()]


_ROUTE_QUERY_FN: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "payment": _payment_rows,
    "refund": _refund_rows,
    "item_delivery": _item_delivery_rows,
    "gacha": _gacha_rows,
    "abuse": _abuse_rows,
    "outage": _outage_rows,
    "policy": _policy_rows,
}


def _context_for_route(route: QueryRoute, state: OperationState) -> list[dict[str, Any]]:
    user_id = state.ticket.user_id or state.ticket.metadata.get("user_id")
    account_id = state.ticket.metadata.get("account_id")
    query_fn = _ROUTE_QUERY_FN.get(route, _policy_rows)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return query_fn(cur, user_id=user_id, account_id=account_id, ticket_id=_ticket_key(state))


def _insert_analysis(state: OperationState) -> int:
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
                    _ticket_key(state),
                    state.analysis.query_route,
                    state.ticket.responder_type,
                    _query_text(state),
                    state.analysis.risk_level,
                    None,
                    state.analysis.target_route,
                    state.analysis.summary,
                ),
            )
            return cast(int, cur.fetchone()[0])


def _insert_draft(state: OperationState, analysis_id: int) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO answer_draft (
                    ticket_id, analysis_id, draft_text, prompt_version, created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING draft_id
                """,
                (
                    _ticket_key(state),
                    analysis_id,
                    state.answer_draft or state.urgent_draft,
                    "operation-workflow-v3",
                ),
            )
            return cast(int, cur.fetchone()[0])


def _insert_evidence_docs(state: OperationState, draft_id: int) -> None:
    cited_ids = set(state.evidence_doc_ids)
    cited_docs = [doc for doc in state.retrieved_docs if doc.doc_id in cited_ids]
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


def _insert_safety_result(state: OperationState, draft_id: int) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
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
                    1.0 if state.safety_result.hallucination_detected else 0.0,
                    1.0 if state.safety_result.unsafe_expression_detected else 0.0,
                    1.0 if state.safety_result.policy_violation_detected else 0.0,
                    1.0 if state.safety_result.evidence_matched else 0.0,
                    state.approval_route,
                    "\n".join(state.safety_result.reasons),
                    state.retry_count or 0,
                ),
            )
            return cast(int, cur.fetchone()[0])


def _insert_final_response(state: OperationState, draft_id: int) -> int:
    final_answer = state.edited_answer or state.answer_draft or state.urgent_draft
    if not final_answer:
        raise ValueError("finalize requires final answer text for approved route")
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
                (
                    _ticket_key(state),
                    draft_id,
                    final_answer,
                    state.approval_route,
                ),
            )
            return cast(int, cur.fetchone()[0])


def _insert_notification(state: OperationState) -> int:
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
                (
                    _ticket_key(state),
                    "operation",
                    "pending",
                    state.urgent_draft or state.answer_draft,
                ),
            )
            return cast(int, cur.fetchone()[0])


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
        context_node_name=CONTEXT_NODE_BY_ROUTE[route],
    )
    return result.model_dump()


def drafting_agent(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = run_drafting_agent(current)
    answer_draft = response.customer_answer.strip() if response.customer_answer else None
    urgent_draft = response.urgent_alert_message.strip() if response.urgent_alert_message else None
    operator_handoff = response.operator_handoff_answer.strip() if response.operator_handoff_answer else None
    valid_ids = {doc.doc_id for doc in current.retrieved_docs if doc.doc_id}
    filtered_ids = [doc_id for doc_id in response.evidence_doc_ids if doc_id in valid_ids]
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
            decision=cast(HumanDecision, decision),
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

    _update_ticket_status(ticket_id, "human_review_pending")
    update |= {"status": "human_review_pending"}
    return update


NODE_FUNCTIONS: dict[str, NodeHandler] = {
    node_name: _with_node_logging(node_name, node_handler)
    for node_name, node_handler in {
        "load_ticket": load_ticket,
        "intake_agent": intake_agent,
        "context_agent": context_agent,
        "drafting_agent": drafting_agent,
        "review_agent": review_agent,
        "review": review,
        "finalize": finalize,
    }.items()
}
