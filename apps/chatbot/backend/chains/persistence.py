from __future__ import annotations

import json
from typing import Any

from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_answer_draft, write_evidence_docs


def _write_answer_draft(payload: dict[str, Any]) -> dict[str, Any]:
    result = write_answer_draft.invoke({"payload": payload})
    return json.loads(result) if isinstance(result, str) else result


def _write_evidence_doc(payload: dict[str, Any]) -> dict[str, Any]:
    result = write_evidence_docs.invoke({"payload": payload})
    return json.loads(result) if isinstance(result, str) else result


def _as_result(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


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
        "source_id": f"{state.get('reasoning_node') or 'unknown'}_generated_draft",
        "evidence_text": state.get("draft_text") or "",
        "relevance_score": 1.0,
        "retrieval_rank": 1,
    }


def _persist_evidence(draft_id: int, state: ChatbotState) -> tuple[int, list[dict[str, Any]]]:
    retrieved_documents = state.get("retrieved_documents") or []
    evidence_payloads = _evidence_payloads_from_retrieved_documents(
        draft_id=draft_id,
        documents=retrieved_documents,
    )
    if not evidence_payloads and str(state.get("draft_text") or "").strip():
        evidence_payloads = [_fallback_evidence_payload(draft_id=draft_id, state=state)]

    results = []
    for payload in evidence_payloads:
        results.append(_write_evidence_doc(payload))

    return len(evidence_payloads), results


def draft_persistence_node(state: ChatbotState) -> dict:
    """Persist the generated answer draft and the evidence used to create it."""
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="draft_persistence",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )

    draft_result = _write_answer_draft(
        {
            "ticket_id": state["ticket_id"],
            "draft_text": state["draft_text"],
        }
    )
    draft_result = _as_result(draft_result)
    draft_id = draft_result.get("draft_id")
    evidence_count = 0
    evidence_results: list[dict[str, Any]] = []
    if draft_id is not None:
        evidence_count, evidence_results = _persist_evidence(int(draft_id), state)

    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name="draft_persistence",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={
            "draft_id": draft_id,
            "evidence_count": evidence_count,
            "draft_stored": draft_result.get("stored"),
        },
    )

    return {"draft_id": draft_id, "evidence_count": evidence_count}
