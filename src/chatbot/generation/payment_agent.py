from __future__ import annotations

import json
from typing import Any

from chatbot.agent import invoke_payment_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import PAYMENT_POLICY
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.repository.operation_log_repository import collect_payment_context_by_user
from chatbot.schemas import ChatbotState


def _compact_row(row: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in row.items() if value is not None)


def _payment_context_to_evidence(context: dict[str, Any]) -> list[dict[str, Any]]:
    data = context.get("data") or {}
    evidence: list[dict[str, Any]] = []
    rank = 1
    for source_type in ("payments", "refunds", "item_delivery_logs", "gacha_logs"):
        rows = data.get(source_type) or []
        for row in rows:
            source_id = (
                row.get("payment_id")
                or row.get("refund_id")
                or row.get("delivery_id")
                or row.get("gacha_id")
                or row.get("account_id")
            )
            evidence.append(
                {
                    "chunk_id": f"{source_type}:{source_id}:{rank}",
                    "document_id": str(source_id or rank),
                    "source_type": source_type,
                    "category": "결제",
                    "title": f"{source_type} record",
                    "chunk_text": _compact_row(row),
                    "score": 1.0,
                    "retrieval_rank": rank,
                }
            )
            rank += 1
    return evidence


def _payment_context_message(context: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "Payment DB context scoped to the logged-in user_id only. "
            "Use this evidence before answering payment/refund/item delivery/gacha questions. "
            "Do not use user-provided account_id or payment_id unless it appears in this context.\n\n"
            f"{json.dumps(context, ensure_ascii=False, default=str)}"
        ),
    }


def _collect_payment_context(state: ChatbotState) -> dict[str, Any]:
    user_id = state.get("user_id")
    if user_id is None:
        return {
            "status": "skipped",
            "reason": "missing_user_id",
            "data": {
                "accounts": [],
                "payments": [],
                "refunds": [],
                "item_delivery_logs": [],
                "gacha_logs": [],
            },
            "counts": {},
            "count": 0,
        }
    return collect_payment_context_by_user(user_id=int(user_id), account_id=state.get("account_id"))


def payment_agent_node(state: ChatbotState) -> dict:
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    payment_context = _collect_payment_context(state)
    payment_evidence = _payment_context_to_evidence(payment_context)
    agent_state = dict(state)
    agent_state["payment_context"] = payment_context
    agent_state["retrieved_documents"] = payment_evidence
    agent_state["messages"] = [
        *list(state.get("messages") or []),
        _payment_context_message(payment_context),
    ]
    result = invoke_payment_agent(agent_state)
    update = build_draft_update(state, result, PAYMENT_POLICY.name)
    update["payment_context"] = payment_context
    update["retrieved_documents"] = payment_evidence
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={
            "draft_length": len(update.get("draft_text") or ""),
            "payment_context_count": payment_context.get("count"),
            "payment_evidence_count": len(payment_evidence),
        },
    )
    return update
