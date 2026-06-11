from __future__ import annotations

import json
from typing import Any

from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.repository.draft_repository import save_answer_draft, save_evidence_docs
from chatbot.schemas import ChatbotState


def _write_answer_draft(payload: dict[str, Any]) -> dict[str, Any]:
    return save_answer_draft(payload)


def _write_evidence_doc(payload: dict[str, Any]) -> dict[str, Any]:
    return save_evidence_docs(payload)


def _as_result(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def _evidence_payloads_from_retrieved_documents(
    *,
    draft_id: int,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # RAG/DB 검색 결과를 evidence_docs 테이블에 저장할 payload 형태로 바꾼다.
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
    # 검색 근거가 없는 agent 답변도 초안과 연결될 수 있게 최소 근거 레코드를 만든다.
    return {
        "draft_id": draft_id,
        "source_type": "agent",
        "source_id": f"{state.get('reasoning_node') or 'unknown'}_generated_draft",
        "evidence_text": state.get("draft_text") or "",
        "relevance_score": 1.0,
        "retrieval_rank": 1,
    }


def _persist_evidence(draft_id: int, state: ChatbotState) -> tuple[int, list[dict[str, Any]]]:
    # 2단계: 검색 문서가 있으면 문서 근거를 저장하고, 없으면 생성 초안 자체를 fallback 근거로 저장한다.
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
    # 1단계: category agent가 만든 draft_text를 answer_draft에 먼저 저장한다.
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
        # 3단계: 초안 저장에 성공하면 초안 생성에 사용한 evidence를 draft_id와 연결한다.
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
