from __future__ import annotations

from tests.chatbot._hybrid_retrieval_cases import *  # noqa: F403
from tests.chatbot._persistence_evidence_cases import *  # noqa: F403

from chatbot.generation import faq_agent
from chatbot.retrieval.vector_tools import RetrievalQuery


def _retrieval_query() -> RetrievalQuery:
    return RetrievalQuery(
        query_text="payment item delivery",
        preferred_source_types=["hoyoverse_qna_common"],
        preferred_categories=["결제_관련_이슈"],
    )


def _state() -> dict:
    return {
        "ticket_id": 123,
        "raw_query": "payment item delivery",
        "enriched_query": "payment item delivery",
        "category": "FAQ",
        "routing_target": "rag_reply",
        "retry_count": 0,
    }


def test_run_faq_rag_blocks_llm_when_no_documents(monkeypatch) -> None:
    failed_payloads = []

    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", lambda text: _retrieval_query())
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: [])
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_write_failed_query", lambda payload: failed_payloads.append(payload) or "{}")

    def fail_generate(*args, **kwargs):
        raise AssertionError("LLM must not be called without evidence")

    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", fail_generate)

    result = faq_agent.run_faq_rag(_state())

    assert result["faq_failure_reason"] == "no_retrieved_documents"
    assert result["retrieved_documents"] == []
    assert failed_payloads


def test_run_faq_rag_skips_retrieval_when_intent_says_rag_is_not_needed(monkeypatch) -> None:
    failed_payloads = []

    def fail_enrich(*args, **kwargs):
        raise AssertionError("RAG should not run when intent gate says should_use_rag=false")

    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", fail_enrich)
    monkeypatch.setattr(faq_agent, "_write_failed_query", lambda payload: failed_payloads.append(payload) or "{}")

    result = faq_agent.run_faq_rag(
        {
            **_state(),
            "raw_query": "게임 왜 이따위임?",
            "enriched_query": "게임 문제 해결 방법",
            "is_actionable": False,
            "should_use_rag": False,
            "fallback_reason": "low_information_complaint",
        }
    )

    assert result["draft_text"] == faq_agent.SAFE_FALLBACK_RESPONSE
    assert result["retrieved_documents"] == []
    assert result["faq_failure_reason"] == "low_information_complaint"
    assert failed_payloads[0]["reason"] == "low_information_complaint"


def test_run_faq_rag_blocks_answer_when_relevance_gate_fails(monkeypatch) -> None:
    failed_payloads = []
    docs = [
        {
            "chunk_id": "doc-1",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_common",
            "category": "게임_문제",
            "title": "별바다 세계 필터 기능 문제",
            "chunk_text": "특정 상황에서 필터 기능이 올바르게 작동하지 않을 수 있습니다.",
            "score": 0.02,
            "cosine_score": 0.2,
            "bm25_score": 0.0,
            "field_match_score": 0.0,
        }
    ]

    monkeypatch.setenv("FAQ_MIN_FIELD_MATCH_SCORE", "0.01")
    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", lambda text: _retrieval_query())
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: docs)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_write_failed_query", lambda payload: failed_payloads.append(payload) or "{}")
    monkeypatch.setattr(
        faq_agent,
        "_generate_evidence_answer",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM must not answer weakly related evidence")),
    )

    result = faq_agent.run_faq_rag(_state())

    assert result["draft_text"] == faq_agent.SAFE_FALLBACK_RESPONSE
    assert result["faq_failure_reason"] == "retrieval_relevance_gate_failed"
    assert failed_payloads[0]["reason"] == "retrieval_relevance_gate_failed"


def test_run_faq_rag_generates_once_with_evidence(monkeypatch) -> None:
    calls = []
    docs = [
        {
            "chunk_id": "doc-1",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_common",
            "category": "결제_관련_이슈",
            "title": "payment guide",
            "chunk_text": "payment item delivery can be checked in logs",
            "score": 0.03,
            "cosine_score": 0.9,
            "bm25_score": 1.2,
        }
    ]

    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", lambda text: _retrieval_query())
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: docs)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(
        faq_agent,
        "_generate_evidence_answer",
        lambda **kwargs: calls.append(kwargs) or "answer from evidence",
    )

    result = faq_agent.run_faq_rag(_state())

    assert result["draft_text"] == "answer from evidence"
    assert result["faq_failure_reason"] is None
    assert result["retrieval_enrichment"]["query_text"] == "payment item delivery"
    assert result["retrieval_enrichment"]["preferred_source_types"] == ["hoyoverse_qna_common"]
    assert len(calls) == 1
    assert calls[0]["original_query"] == "payment item delivery"
    assert calls[0]["retrieval_query"] == "payment item delivery"


def test_run_faq_rag_answers_with_canonical_retrieval_query(monkeypatch) -> None:
    calls = []
    docs = [
        {
            "chunk_id": "doc-1",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_onlygenshin",
            "category": "계정_문제",
            "title": "게임 진행도는 어떻게 리셋할 수 있나요?",
            "chunk_text": "로그인 화면 오른쪽 하단에서 로그아웃을 선택하신 뒤 새로운 계정으로 로그인하면 새로운 게임을 시작할 수 있습니다",
            "score": 0.08,
            "cosine_score": 0.9,
            "bm25_score": 2.1,
        }
    ]

    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(
        faq_agent,
        "enrich_retrieval_query",
        lambda text: RetrievalQuery(
            query_text="게임 진행도 리셋 방법",
            preferred_source_types=["hoyoverse_qna_onlygenshin"],
            preferred_categories=["계정_문제"],
        ),
    )
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: docs)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", lambda **kwargs: calls.append(kwargs) or "진행도 리셋 답변")

    result = faq_agent.run_faq_rag(
        {
            **_state(),
            "raw_query": "스토리 초기화 어캐함?",
            "enriched_query": "스토리 초기화 어캐함?",
            "should_use_rag": True,
        }
    )

    assert result["draft_text"] == "진행도 리셋 답변"
    assert result["retrieval_query"] == "게임 진행도 리셋 방법"
    assert calls[0]["original_query"] == "스토리 초기화 어캐함?"
    assert calls[0]["retrieval_query"] == "게임 진행도 리셋 방법"
