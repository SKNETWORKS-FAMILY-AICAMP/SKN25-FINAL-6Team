from __future__ import annotations

import os
from typing import Any

from chatbot.agent import invoke_bug_agent
from chatbot.generation.faq_agent import _embed_query, _generate_evidence_answer, _rerank_documents
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import BUG_POLICY
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, EVENT_TOOL_COMPLETED, log_event
from chatbot.schemas import ChatbotState
from common.retrieval.vector_tools import RetrievalQuery, search_document_chunks


BUG_REPRODUCTION_FORM_RESPONSE = """문제 확인을 위해 아래 항목을 작성해 주세요.

발생 시점:
오류 메시지:
사용 기기/OS:
오류 내용:"""

BUG_ACCEPTED_RESPONSE = """제공해주신 내용 기준으로 오류 문의가 접수 완료되었습니다.

접수 상태:
접수 완료

저장 내용:
초기 문의와 작성해주신 재현 정보가 문의 내역에 함께 저장되었습니다.

검토 안내:
이후 로그 및 재현 조건 검토가 진행됩니다."""


def _active_query(state: ChatbotState) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "").strip()


def _bug_faq_category() -> str:
    return os.environ.get("BUG_FAQ_CATEGORY", "bug_faq").strip()


def _best_cosine_score(documents: list[dict[str, Any]]) -> float:
    scores = []
    for document in documents:
        try:
            scores.append(float(document.get("cosine_score") or 0))
        except (TypeError, ValueError):
            scores.append(0.0)
    return max(scores or [0.0])


def _best_bm25_score(documents: list[dict[str, Any]]) -> float:
    scores = []
    for document in documents:
        try:
            scores.append(float(document.get("bm25_score") or 0))
        except (TypeError, ValueError):
            scores.append(0.0)
    return max(scores or [0.0])


def _log_bug_faq_precheck(state: ChatbotState, *, status: str, metadata: dict[str, Any]) -> None:
    log_event(
        EVENT_TOOL_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        tool_name="bug_faq_precheck",
        status=status,
        metadata=metadata,
    )


def _run_bug_faq_precheck(state: ChatbotState) -> dict[str, Any] | None:
    if state.get("bug_collection_status") != "collecting":
        return None

    bug_faq_category = _bug_faq_category()
    query = _active_query(state)
    if not bug_faq_category or not query:
        _log_bug_faq_precheck(
            state,
            status="skipped",
            metadata={"reason": "missing_category_or_query", "bug_faq_category": bug_faq_category, "query": query},
        )
        return None

    try:
        embedding_json = _embed_query(query)
        candidate_top_k = int(os.environ.get("BUG_FAQ_CANDIDATE_TOP_K", "8"))
        final_top_k = int(os.environ.get("BUG_FAQ_TOP_K", "3"))
        documents = search_document_chunks(
            embedding_json=embedding_json,
            query_text=query,
            top_k=candidate_top_k,
            prefer_faq=False,
            enrichment=RetrievalQuery(
                query_text=query,
                preferred_source_types=[],
                preferred_categories=[bug_faq_category],
            ),
        )
        documents = _rerank_documents(documents, query)[:final_top_k]
        documents = [doc for doc in documents if str(doc.get("category") or "") == bug_faq_category]
        best_cosine = _best_cosine_score(documents)
        best_bm25 = _best_bm25_score(documents)
    except Exception as exc:
        _log_bug_faq_precheck(
            state,
            status="error",
            metadata={
                "reason": "retrieval_failed",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return None

    if not documents:
        _log_bug_faq_precheck(
            state,
            status="skipped",
            metadata={
                "reason": "no_bug_faq_document",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "document_count": len(documents),
                "best_cosine_score": best_cosine,
                "best_bm25_score": best_bm25,
                "top_documents": [
                    {
                        "document_id": doc.get("document_id"),
                        "chunk_id": doc.get("chunk_id"),
                        "category": doc.get("category"),
                        "title": doc.get("title"),
                        "cosine_score": doc.get("cosine_score"),
                        "score": doc.get("score"),
                    }
                    for doc in documents[:3]
                ],
            },
        )
        return None

    try:
        answer = _generate_evidence_answer(
            original_query=query,
            retrieval_query=query,
            documents=documents,
        )
    except Exception as exc:
        _log_bug_faq_precheck(
            state,
            status="error",
            metadata={
                "reason": "answer_generation_failed",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "document_count": len(documents),
                "best_cosine_score": best_cosine,
                "best_bm25_score": best_bm25,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return None
    _log_bug_faq_precheck(
        state,
        status="ok",
        metadata={
            "reason": "matched",
            "bug_faq_category": bug_faq_category,
            "query": query,
            "document_count": len(documents),
            "best_cosine_score": best_cosine,
            "best_bm25_score": best_bm25,
        },
    )
    return {
        "draft_text": answer,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": BUG_POLICY.name,
        "bug_collection_status": None,
        "retrieved_documents": documents,
        "retrieved_count": len(documents),
        "retrieval_query": query,
        "retrieval_enrichment": {
            "bug_faq_category": bug_faq_category,
            "best_cosine_score": best_cosine,
            "best_bm25_score": best_bm25,
        },
        "faq_failure_reason": None,
    }


def bug_agent_node(state: ChatbotState) -> dict:
    # 1단계: 버그 문의는 자동 확정 답변보다 재현 정보 수집/검토 안내 중심으로 초안을 만든다.
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    bug_faq_update = _run_bug_faq_precheck(state)
    if bug_faq_update is not None:
        update = bug_faq_update
    elif state.get("bug_collection_status") == "collecting":
        update = {
            "draft_text": BUG_REPRODUCTION_FORM_RESPONSE,
            "retry_count": state["retry_count"],
            "category": state["category"],
            "routing_target": state["routing_target"],
            "reasoning_node": BUG_POLICY.name,
            "safety_action": "AUTO_RESPONSE",
            "safety_passed": True,
            "review_required": False,
        }
    elif state.get("bug_collection_status") == "ready_for_review":
        update = {
            "draft_text": BUG_ACCEPTED_RESPONSE,
            "retry_count": state["retry_count"],
            "category": state["category"],
            "routing_target": state["routing_target"],
            "reasoning_node": BUG_POLICY.name,
            "safety_action": "REVIEW_REQUIRED",
            "safety_passed": True,
            "review_required": True,
        }
    else:
        result = invoke_bug_agent(state)
        update = build_draft_update(state, result, BUG_POLICY.name)

    # 2단계: 생성된 버그 초안 길이를 기록하고 공통 draft_persistence 노드로 넘긴다.
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_length": len(update.get("draft_text") or "")},
    )
    return update
