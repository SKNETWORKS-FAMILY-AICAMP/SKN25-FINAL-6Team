"""Node and router declarations for the operation LangGraph workflow."""

from __future__ import annotations

from typing import Any, Callable, Literal, cast

from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from src.common.db.connection import db_connection
from src.common.llm.client import invoke_structured_llm

from .prompts import (
    ANALYSIS_PROMPT,
    ANSWER_PROMPT,
    HUMAN_REVIEW_PROMPT,
    QUERY_ROUTER_PROMPT,
    SAFETY_PROMPT,
    SYSTEM_PROMPT,
    URGENT_PROMPT,
    AnswerDraftResponse,
    HumanReviewResponse,
    QueryRoutingResponse,
    SafetyReviewResponse,
    TicketAnalysisResponse,
    UrgentDraftResponse,
    render_state,
)
from .state import (
    AnalysisResult,
    ApprovalRoute,
    EvidenceDocument,
    HumanDecision,
    HumanReviewResult,
    OperationState,
    QueryRoute,
    SafetyResult,
    TargetRoute,
    Ticket,
)


StateUpdate = dict[str, Any] | None
NodeHandler = Callable[[OperationState], StateUpdate]
AfterDraftRoute = Literal["save_evidence_docs", "approval_gate"]


class DbRow(BaseModel):
    """Database row stored in workflow context."""

    model_config = ConfigDict(extra="allow")


QUERY_ROUTES: tuple[QueryRoute, ...] = (
    "payment",
    "refund",
    "item_delivery",
    "gacha",
    "policy",
    "abuse",
    "outage",
)

CONTEXT_NODE_BY_ROUTE: dict[QueryRoute, str] = {
    "payment": "payment_context_node",
    "refund": "refund_context_node",
    "item_delivery": "item_delivery_context_node",
    "gacha": "gacha_context_node",
    "policy": "policy_context_node",
    "abuse": "abuse_context_node",
    "outage": "outage_context_node",
}


def _state(state: OperationState | dict[str, Any]) -> OperationState:
    return OperationState.model_validate(state)


def _dump_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [DbRow.model_validate(row).model_dump(mode="json") for row in rows]


def _next_id(table_name: str, column_name: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COALESCE(MAX({column_name}), 0) + 1 FROM {table_name}")
            return cast(int, cur.fetchone()[0])


def _next_id_from_cursor(cur: Any, table_name: str, column_name: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX({column_name}), 0) + 1 FROM {table_name}")
    return cast(int, cur.fetchone()[0])


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
            return dict(cur.fetchone())


def _context_for_route(route: QueryRoute, state: OperationState) -> list[dict[str, Any]]:
    ticket_id = state.ticket_id or state.ticket.ticket_id
    user_id = state.ticket.user_id or state.ticket.metadata.get("user_id")
    account_id = state.ticket.metadata.get("account_id")
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if route == "payment":
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
            elif route == "refund":
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
            elif route == "item_delivery":
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
            elif route == "gacha":
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
            elif route == "abuse":
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
            elif route == "outage":
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
            else:
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

# 날 닮은너... 너 늬긔야.....
def _add_context(state: OperationState, route: QueryRoute) -> StateUpdate:
    rows = _dump_rows(_context_for_route(route, state))
    context = state.context | {route: rows}
    return {"context": context, "context_nodes": [*state.context_nodes, CONTEXT_NODE_BY_ROUTE[route]]}

## 여기서부터 node 시작
def load_ticket(state: OperationState) -> StateUpdate:
    current = _state(state)
    if current.ticket_id:
        row = _fetch_ticket(current.ticket_id)
        ticket = Ticket(
            ticket_id=str(row.get("ticket_id")),
            user_id=str(row.get("user_id")),
            title=row.get("title"),
            body=row.get("raw_query"),
            channel=row.get("source_type"),
            created_at=str(row.get("inquiry_created_at")) if row.get("inquiry_created_at") else None,
            metadata=row,
        )
        return {"ticket": ticket, "query_text": ticket.body, "status": row.get("status")}
    query_text = current.query_text or current.ticket.body or current.ticket.title
    return {"query_text": query_text}


def query_router(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=QUERY_ROUTER_PROMPT.format(state_json=render_state(current)),
        response_model=QueryRoutingResponse,
    )
    return {"query_route": response.query_route, "query_route_reason": response.route_reason}


def payment_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "payment")


def refund_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "refund")


def item_delivery_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "item_delivery")


def gacha_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "gacha")


def policy_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "policy")


def abuse_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "abuse")


def outage_context_node(state: OperationState) -> StateUpdate:
    return _add_context(_state(state), "outage")


def analyze_ticket(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=ANALYSIS_PROMPT.format(state_json=render_state(current)),
        response_model=TicketAnalysisResponse,
    )
    analysis = AnalysisResult(
        query_route=response.query_route,
        target_route=response.target_route,
        risk_level=response.risk_level,
        risk_reason=response.risk_reason,
        summary=response.summary,
        required_actions=response.required_actions,
    )
    return {"analysis": analysis, "query_route": response.query_route, "target_route": response.target_route}


def save_analysis(state: OperationState) -> StateUpdate:
    current = _state(state)
    analysis_id = _next_id("ticket_analysis", "analysis_id")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ticket_analysis (
                    analysis_id, ticket_id, category, responder_type, enriched_query,
                    risk_level, sentiment, routing_target, summary, analyzed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    analysis_id,
                    current.ticket_id or current.ticket.ticket_id,
                    current.analysis.query_route,
                    current.target_route,
                    current.query_text,
                    current.analysis.risk_level,
                    None,
                    current.analysis.target_route,
                    current.analysis.summary,
                ),
            )
    return {"analysis_id": analysis_id}


def rag_retrieve_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    with db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.document_id,
                    d.source_type,
                    d.category,
                    d.title,
                    c.chunk_text,
                    ts_rank_cd(to_tsvector('simple', c.chunk_text), plainto_tsquery('simple', %s)) AS score
                FROM documents_chunks c
                JOIN documents d ON d.documents_id = c.document_id
                WHERE to_tsvector('simple', c.chunk_text) @@ plainto_tsquery('simple', %s)
                   OR c.chunk_text ILIKE %s
                   OR d.title ILIKE %s
                ORDER BY score DESC NULLS LAST, c.created_at DESC NULLS LAST
                LIMIT 8
                """,
                (current.query_text, current.query_text, f"%{current.query_text}%", f"%{current.query_text}%"),
            )
            rows = [dict(row) for row in cur.fetchall()]
    docs = [
        EvidenceDocument(
            doc_id=row.get("chunk_id"),
            source=row.get("source_type"),
            title=row.get("title"),
            content=row.get("chunk_text"),
            score=float(row.get("score") or 0),
            metadata=row,
        )
        for row in rows
    ]
    return {"retrieved_docs": docs, "evidence_doc_ids": [doc.doc_id for doc in docs if doc.doc_id]}


def generate_answer_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=ANSWER_PROMPT.format(state_json=render_state(current)),
        response_model=AnswerDraftResponse,
    )
    return {"answer_draft": response.answer_draft, "evidence_doc_ids": response.evidence_doc_ids}


def urgent_draft_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=URGENT_PROMPT.format(state_json=render_state(current)),
        response_model=UrgentDraftResponse,
    )
    return {"urgent_draft": response.urgent_draft, "answer_draft": response.urgent_draft}


def save_draft_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    draft_id = _next_id("answer_draft", "draft_id")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO answer_draft (
                    draft_id, ticket_id, analysis_id, draft_text, prompt_version, created_at
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    draft_id,
                    current.ticket_id or current.ticket.ticket_id,
                    current.analysis_id,
                    current.answer_draft or current.urgent_draft,
                    "operation-workflow",
                ),
            )
    return {"draft_id": draft_id}


def save_evidence_docs_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    with db_connection() as conn:
        with conn.cursor() as cur:
            for rank, document in enumerate(current.retrieved_docs, start=1):
                evidence_id = _next_id_from_cursor(cur, "evidence_docs", "evidence_id")
                cur.execute(
                    """
                    INSERT INTO evidence_docs (
                        evidence_id, draft_id, source_type, source_id,
                        evidence_text, relevance_score, retrieval_rank
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        evidence_id,
                        current.draft_id,
                        document.source,
                        document.doc_id,
                        document.content,
                        document.score,
                        rank,
                    ),
                )
    return {"status": "evidence_saved"}


def approval_gate_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=SAFETY_PROMPT.format(state_json=render_state(current)),
        response_model=SafetyReviewResponse,
    )
    safety = SafetyResult(
        approved=response.approved,
        evidence_matched=response.evidence_matched,
        hallucination_detected=response.hallucination_detected,
        policy_violation_detected=response.policy_violation_detected,
        unsafe_expression_detected=response.unsafe_expression_detected,
        reasons=response.reasons,
    )
    if response.policy_violation_detected or current.analysis.risk_level == "critical":
        approval_route: ApprovalRoute = "urgent_alert"
    elif response.approved:
        approval_route = "approved"
    else:
        approval_route = "human_review"
    return {"safety_result": safety, "approval_route": approval_route}


def save_safety_result_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    safety_id = _next_id("safety_results", "safety_id")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO safety_results (
                    safety_id, draft_id, hallucination_score, toxicity_score,
                    policy_violation_score, factuality_score, checked_at,
                    safety_action, safety_reason, retry_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                """,
                (
                    safety_id,
                    current.draft_id,
                    1.0 if current.safety_result.hallucination_detected else 0.0,
                    1.0 if current.safety_result.unsafe_expression_detected else 0.0,
                    1.0 if current.safety_result.policy_violation_detected else 0.0,
                    1.0 if current.safety_result.evidence_matched else 0.0,
                    current.approval_route,
                    "\n".join(current.safety_result.reasons),
                    current.retry_count or 0,
                ),
            )
    return {"safety_id": safety_id}


def publish_final_answer_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    final_answer = current.edited_answer or current.answer_draft or current.urgent_draft
    response_id = _next_id("final_response", "response_id")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO final_response (
                    response_id, ticket_id, draft_id, final_text, safety_action, created_at
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    response_id,
                    current.ticket_id or current.ticket.ticket_id,
                    current.draft_id,
                    final_answer,
                    current.approval_route,
                ),
            )
            cur.execute(
                """
                UPDATE qa_ticket
                SET status = %s
                WHERE ticket_id = %s
                """,
                ("closed", current.ticket_id or current.ticket.ticket_id),
            )
    return {"final_answer": final_answer, "response_id": response_id, "status": "closed"}


def human_review_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    response = invoke_structured_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=HUMAN_REVIEW_PROMPT.format(state_json=render_state(current)),
        response_model=HumanReviewResponse,
    )
    human_review = HumanReviewResult(
        decision=cast(HumanDecision, response.decision),
        reason=response.reason,
        edited_answer=response.edited_answer,
    )
    return {
        "human_decision": human_review.decision,
        "human_review": human_review,
        "edited_answer": human_review.edited_answer,
    }


def retry_routing_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    retry_count = (current.retry_count or 0) + 1
    return {
        "retry_count": retry_count,
        "answer_draft": None,
        "urgent_draft": None,
        "approval_route": None,
        "human_decision": None,
        "metadata": current.metadata | {"retry_reason": current.human_review.reason},
    }


def edit_answer_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    return {"edited_answer": current.human_review.edited_answer}


def save_final_edit_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    return {"final_answer": current.edited_answer or current.answer_draft}


def urgent_alert_node(state: OperationState) -> StateUpdate:
    current = _state(state)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notification_logs (
                    notification_id, ticket_id, channel, status, message, sent_at
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    _next_id_from_cursor(cur, "notification_logs", "notification_id"),
                    current.ticket_id or current.ticket.ticket_id,
                    "operation",
                    "pending",
                    current.urgent_draft or current.answer_draft,
                ),
            )
    return {"status": "urgent_alert_pending"}


def route_by_query(state: OperationState) -> QueryRoute:
    current = _state(state)
    return cast(QueryRoute, current.query_route)


def route_by_target(state: OperationState) -> TargetRoute:
    current = _state(state)
    return cast(TargetRoute, current.target_route or current.analysis.target_route)


def route_after_save_draft(state: OperationState) -> AfterDraftRoute:
    current = _state(state)
    if current.retrieved_docs:
        return "save_evidence_docs"
    return "approval_gate"


def route_by_approval(state: OperationState) -> ApprovalRoute:
    current = _state(state)
    return cast(ApprovalRoute, current.approval_route)


def route_by_human_decision(state: OperationState) -> HumanDecision:
    current = _state(state)
    return cast(HumanDecision, current.human_decision)


NODE_FUNCTIONS: dict[str, NodeHandler] = {
    "load_ticket": load_ticket,
    "query_router": query_router,
    "payment_context_node": payment_context_node,
    "refund_context_node": refund_context_node,
    "item_delivery_context_node": item_delivery_context_node,
    "gacha_context_node": gacha_context_node,
    "policy_context_node": policy_context_node,
    "abuse_context_node": abuse_context_node,
    "outage_context_node": outage_context_node,
    "analyze_ticket": analyze_ticket,
    "save_analysis": save_analysis,
    "rag_retrieve_node": rag_retrieve_node,
    "generate_answer_node": generate_answer_node,
    "urgent_draft_node": urgent_draft_node,
    "save_draft_node": save_draft_node,
    "save_evidence_docs_node": save_evidence_docs_node,
    "approval_gate_node": approval_gate_node,
    "save_safety_result_node": save_safety_result_node,
    "publish_final_answer_node": publish_final_answer_node,
    "human_review_node": human_review_node,
    "retry_routing_node": retry_routing_node,
    "edit_answer_node": edit_answer_node,
    "save_final_edit_node": save_final_edit_node,
    "urgent_alert_node": urgent_alert_node,
}
