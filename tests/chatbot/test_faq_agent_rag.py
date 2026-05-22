from __future__ import annotations

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
        lambda query, documents: calls.append((query, documents)) or "answer from evidence",
    )

    result = faq_agent.run_faq_rag(_state())

    assert result["draft_text"] == "answer from evidence"
    assert result["faq_failure_reason"] is None
    assert result["retrieval_enrichment"]["query_text"] == "payment item delivery"
    assert result["retrieval_enrichment"]["preferred_source_types"] == ["hoyoverse_qna_common"]
    assert len(calls) == 1
