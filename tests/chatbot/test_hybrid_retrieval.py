from __future__ import annotations

from chatbot.retrieval import vector_tools
from chatbot.retrieval.vector_tools import hybrid_rank_documents, refine_query_text, search_document_chunks


def test_refine_query_text_deduplicates_terms() -> None:
    query = "hello hello payment payment item delivery help"

    assert refine_query_text(query) == "hello payment item delivery help"


def test_hybrid_rank_documents_combines_bm25_and_cosine() -> None:
    rows = [
        {
            "chunk_id": "dense-match",
            "document_id": "doc-1",
            "source_type": "faq",
            "category": "account",
            "title": "account guide",
            "chunk_text": "account linking and data deletion process",
            "embedding_vector": "[1.0,0.0]",
        },
        {
            "chunk_id": "keyword-match",
            "document_id": "doc-2",
            "source_type": "faq",
            "category": "payment",
            "title": "payment delivery guide",
            "chunk_text": "payment item delivery missing check method",
            "embedding_vector": "[0.0,1.0]",
        },
        {
            "chunk_id": "weak",
            "document_id": "doc-3",
            "source_type": "notice",
            "category": "event",
            "title": "event",
            "chunk_text": "attendance reward event",
            "embedding_vector": "[0.2,0.1]",
        },
    ]

    results = hybrid_rank_documents(
        query_vector=[1.0, 0.0],
        query_text="payment item delivery",
        rows=rows,
        top_k=2,
    )

    chunk_ids = {result["chunk_id"] for result in results}
    assert chunk_ids == {"dense-match", "keyword-match"}
    assert all("cosine_score" in result and "bm25_score" in result for result in results)


def test_search_document_chunks_prefers_faq_then_falls_back(monkeypatch) -> None:
    calls = []

    def fake_fetch_candidate_rows(*, retrieval_query, candidate_limit, faq_only, enrichment=None):
        calls.append(faq_only)
        if faq_only:
            return []
        return [
            {
                "chunk_id": "fallback-doc",
                "document_id": "doc-1",
                "source_type": "notice",
                "category": "general",
                "title": "fallback",
                "chunk_text": "payment item delivery fallback",
                "embedding_vector": "[1.0,0.0]",
            }
        ]

    monkeypatch.setattr(vector_tools, "_fetch_candidate_rows", fake_fetch_candidate_rows)

    results = search_document_chunks(
        embedding_json="[1.0,0.0]",
        query_text="payment item delivery",
        top_k=1,
        prefer_faq=True,
    )

    assert calls == [True, False]
    assert results[0]["chunk_id"] == "fallback-doc"
    assert results[0]["candidate_scope"] == "all"
