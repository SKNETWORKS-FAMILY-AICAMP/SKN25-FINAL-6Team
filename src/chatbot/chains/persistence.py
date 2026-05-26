from __future__ import annotations

import json
from typing import Any

from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def _write_answer_draft(payload: dict[str, Any]) -> str:
    return write_answer_draft.invoke({"payload": payload})


def _write_evidence_doc(payload: dict[str, Any]) -> str:
    return write_evidence_docs.invoke({"payload": payload})


def _evidence_payloads_from_retrieved_documents(
    *,
    draft_id: int,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads = []
    for rank, document in enumerate(documents, start=1):
        evidence_text = str(document.get("chunk_text") or "").strip()
        if not evidence_text:
            continue

        source_id = document.get("chunk_id") or document.get("document_id")
        payloads.append(
            {
                "draft_id": draft_id,
                "source_type": document.get("source_type") or "document",
                "source_id": str(source_id) if source_id is not None else None,
                "evidence_text": evidence_text,
                "relevance_score": float(document.get("score") or document.get("cosine_score") or 0.0),
                "retrieval_rank": rank,
            }
        )
    return payloads


def _fallback_evidence_payload(*, draft_id: int, state: ChatbotState) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "source_type": "agent",
        "source_id": f"{state['reasoning_node']}_generated_draft",
        "evidence_text": state["draft_text"],
        "relevance_score": 1.0,
        "retrieval_rank": 1,
    }


def _persist_evidence(draft_id: int, state: ChatbotState) -> int:
    retrieved_documents = state.get("retrieved_documents") or []
    evidence_payloads = _evidence_payloads_from_retrieved_documents(
        draft_id=draft_id,
        documents=retrieved_documents,
    )
    if not evidence_payloads:
        evidence_payloads = [_fallback_evidence_payload(draft_id=draft_id, state=state)]

    for payload in evidence_payloads:
        _write_evidence_doc(payload)

    return len(evidence_payloads)


def draft_persistence_node(state: ChatbotState) -> dict:
    """Persist the generated answer draft and the evidence used to create it."""
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="draft_persistence",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"analysis_id": state.get("analysis_id")},
    )
    draft_result = _write_answer_draft(
        {
            "ticket_id": state["ticket_id"],
            "analysis_id": state["analysis_id"],
            "draft_text": state["draft_text"],
        }
    )
    draft_id = json.loads(draft_result)["draft_id"]

    evidence_count = _persist_evidence(draft_id, state)

    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="draft_persistence",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_id": draft_id, "evidence_count": evidence_count},
    )

    return {"draft_id": draft_id, "evidence_count": evidence_count}
