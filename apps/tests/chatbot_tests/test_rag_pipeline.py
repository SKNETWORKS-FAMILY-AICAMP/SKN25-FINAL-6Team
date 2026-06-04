from __future__ import annotations

import json

from chatbot.chains import persistence
from chatbot.generation import faq_agent
from chatbot.retrieval import cache_store
from common.retrieval import vector_tools
from common.retrieval.vector_tools import RetrievalQuery, hybrid_rank_documents, refine_query_text, search_document_chunks


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
        "normalized_query": "payment item delivery",
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
            "raw_query": "게임이 너무 어려워요.",
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
            "title": "별바다 이벤트 필터 기능 문제",
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


def test_run_faq_rag_retries_with_llm_rewrite_when_first_search_has_no_evidence(monkeypatch) -> None:
    calls = []
    docs_after_rewrite = [
        {
            "chunk_id": "doc-rewrite",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_common",
            "category": "payment",
            "title": "payment item delivery guide",
            "chunk_text": "payment item delivery missing item guide",
            "score": 0.09,
            "cosine_score": 0.8,
            "bm25_score": 1.0,
        }
    ]

    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", lambda text: _retrieval_query())
    monkeypatch.setattr(
        faq_agent,
        "rewrite_query_with_llm",
        lambda **kwargs: {
            "query_text": "missing payment item delivery guide",
            "method": "llm_rewrite",
            "reason": None,
            "model": "test-model",
        },
    )

    def fake_search_document_chunks(**kwargs):
        calls.append(kwargs["query_text"])
        if kwargs["query_text"] == "missing payment item delivery guide":
            return docs_after_rewrite
        return []

    monkeypatch.setattr(faq_agent, "search_document_chunks", fake_search_document_chunks)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", lambda **kwargs: "answer after rewrite")

    result = faq_agent.run_faq_rag(_state())

    assert calls == ["payment item delivery", "missing payment item delivery guide"]
    assert result["draft_text"] == "answer after rewrite"
    assert result["faq_failure_reason"] is None
    assert result["retrieval_query"] == "missing payment item delivery guide"
    assert result["retrieval_enrichment"]["rewrite_fallback"]["method"] == "llm_rewrite"


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


def test_run_faq_rag_reuses_cached_retrieved_documents(monkeypatch) -> None:
    """FAQ/RAG should cache evidence documents while still generating a fresh answer."""
    calls = {"embed": 0, "search": 0, "rerank": 0, "answer": 0}
    cache_events = []
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

    cache_store.clear_cache_for_tests()
    monkeypatch.setenv("FAQ_RETRIEVAL_CACHE_ENABLED", "true")
    monkeypatch.setattr(faq_agent, "enrich_retrieval_query", lambda text: _retrieval_query())
    monkeypatch.setattr(
        faq_agent,
        "log_event",
        lambda event_type, **kwargs: cache_events.append({"event_type": event_type, **kwargs}),
    )

    def fake_embed_query(text):
        calls["embed"] += 1
        return "[1.0,0.0]"

    def fake_search_document_chunks(**kwargs):
        calls["search"] += 1
        return docs

    def fake_rerank_documents(documents, query):
        calls["rerank"] += 1
        return documents

    def fake_generate_evidence_answer(**kwargs):
        calls["answer"] += 1
        return f"answer {calls['answer']}"

    monkeypatch.setattr(faq_agent, "_embed_query", fake_embed_query)
    monkeypatch.setattr(faq_agent, "search_document_chunks", fake_search_document_chunks)
    monkeypatch.setattr(faq_agent, "_rerank_documents", fake_rerank_documents)
    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", fake_generate_evidence_answer)

    first = faq_agent.run_faq_rag(_state())
    second = faq_agent.run_faq_rag(_state())

    assert first["draft_text"] == "answer 1"
    assert second["draft_text"] == "answer 2"
    assert first["retrieved_documents"] == docs
    assert second["retrieved_documents"] == docs
    assert calls == {"embed": 1, "search": 1, "rerank": 1, "answer": 2}
    assert [event["metadata"]["cache_hit"] for event in cache_events] == [False, True]
    assert all(event["tool_name"] == "faq_retrieval_cache" for event in cache_events)


def test_run_faq_rag_prefers_normalized_query_over_legacy_enriched_query(monkeypatch) -> None:
    calls = []
    docs = [
        {
            "chunk_id": "doc-1",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_common",
            "category": "faq",
            "title": "normalized guide",
            "chunk_text": "normalized question answer",
            "score": 0.03,
            "cosine_score": 0.9,
            "bm25_score": 1.2,
        }
    ]

    monkeypatch.setattr(faq_agent, "_embed_query", lambda text: "[1.0,0.0]")
    monkeypatch.setattr(
        faq_agent,
        "enrich_retrieval_query",
        lambda text: calls.append(text) or RetrievalQuery(
            query_text=text,
            preferred_source_types=["hoyoverse_qna_common"],
            preferred_categories=[],
        ),
    )
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: docs)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", lambda **kwargs: "answer")

    result = faq_agent.run_faq_rag(
        {
            **_state(),
            "normalized_query": "normalized question",
            "enriched_query": "legacy enriched question",
        }
    )

    assert calls == ["normalized question"]
    assert result["retrieval_query"] == "normalized question"


def test_run_faq_rag_answers_with_canonical_retrieval_query(monkeypatch) -> None:
    calls = []
    docs = [
        {
            "chunk_id": "doc-1",
            "document_id": "doc",
            "source_type": "hoyoverse_qna_onlygenshin",
            "category": "계정_문제",
            "title": "게임 진행도는 어떻게 초기화할 수 있나요?",
            "chunk_text": "로그인 화면 오른쪽 하단에서 로그아웃을 선택한 뒤 새로운 계정으로 로그인하면 새 게임을 시작할 수 있습니다.",
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
            query_text="게임 진행도 초기화 방법",
            preferred_source_types=["hoyoverse_qna_onlygenshin"],
            preferred_categories=["계정_문제"],
        ),
    )
    monkeypatch.setattr(faq_agent, "search_document_chunks", lambda **kwargs: docs)
    monkeypatch.setattr(faq_agent, "_rerank_documents", lambda documents, query: documents)
    monkeypatch.setattr(faq_agent, "_generate_evidence_answer", lambda **kwargs: calls.append(kwargs) or "진행도 초기화 답변")

    result = faq_agent.run_faq_rag(
        {
            **_state(),
            "raw_query": "스토리 초기화 문의",
            "normalized_query": "스토리 초기화 문의",
            "enriched_query": "스토리 초기화 문의",
            "should_use_rag": True,
        }
    )

    assert result["draft_text"] == "진행도 초기화 답변"
    assert result["retrieval_query"] == "게임 진행도 초기화 방법"
    assert calls[0]["original_query"] == "스토리 초기화 문의"
    assert calls[0]["retrieval_query"] == "게임 진행도 초기화 방법"


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

    def fake_fetch_candidate_rows(*, retrieval_query, candidate_limit, faq_only, enrichment=None, use_query_filter=True):
        calls.append((faq_only, use_query_filter))
        if faq_only and use_query_filter:
            return []
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

    assert calls == [(True, True), (True, False), (False, True)]
    assert results[0]["chunk_id"] == "fallback-doc"
    assert results[0]["candidate_scope"] == "all"


def test_search_document_chunks_adds_broad_faq_candidates_when_query_candidates_are_sparse(monkeypatch) -> None:
    calls = []

    def fake_fetch_candidate_rows(*, retrieval_query, candidate_limit, faq_only, enrichment=None, use_query_filter=True):
        calls.append((faq_only, use_query_filter))
        if use_query_filter:
            return [
                {
                    "chunk_id": "notice",
                    "document_id": "doc-1",
                    "source_type": "naver_cafe_notice",
                    "category": "notice",
                    "title": "payment maintenance",
                    "chunk_text": "payment maintenance notice",
                    "embedding_vector": "[0.0,1.0]",
                }
            ]
        return [
            {
                "chunk_id": "guide",
                "document_id": "doc-2",
                "source_type": "hoyoverse_qna_common",
                "category": "payment",
                "title": "payment guide",
                "chunk_text": "payment item delivery guide",
                "embedding_vector": "[1.0,0.0]",
            }
        ]

    monkeypatch.setattr(vector_tools, "_fetch_candidate_rows", fake_fetch_candidate_rows)
    monkeypatch.setenv("RETRIEVAL_MIN_CANDIDATES", "2")

    results = search_document_chunks(
        embedding_json="[1.0,0.0]",
        query_text="payment item delivery",
        top_k=1,
        prefer_faq=True,
    )

    assert calls == [(True, True), (True, False)]
    assert results[0]["chunk_id"] == "guide"
    assert results[0]["candidate_scope"] == "faq_broad"


def test_hybrid_rank_documents_prefers_qna_over_adjacent_notice_when_scores_are_close() -> None:
    rows = [
        {
            "chunk_id": "notice",
            "document_id": "notice-1",
            "source_type": "naver_cafe_notice",
            "category": "공지",
            "title": "Galaxy Store 결제 시스템 점검 안내",
            "chunk_text": "Galaxy Store 결제 시스템 점검 안내",
            "embedding_vector": "[1.0,0.0]",
        },
        {
            "chunk_id": "qna",
            "document_id": "qna-1",
            "source_type": "hoyoverse_qna_common",
            "category": "결제_관련_이슈",
            "title": "Galaxy Store 결제 관련 문제 해결",
            "chunk_text": "Galaxy Store 결제 관련 문제 해결 방법",
            "embedding_vector": "[0.99,0.01]",
        },
    ]

    results = hybrid_rank_documents(
        query_vector=[1.0, 0.0],
        query_text="Galaxy Store 결제 방법",
        rows=rows,
        top_k=2,
    )

    assert results[0]["chunk_id"] == "qna"


def test_hybrid_rank_documents_boosts_question_title_overlap() -> None:
    rows = [
        {
            "chunk_id": "adjacent",
            "document_id": "doc-1",
            "source_type": "hoyoverse_qna_onlygenshin",
            "category": "client",
            "title": "인터넷에 연결하여 게임을 플레이해야 하나요?",
            "chunk_text": "게임 진행도는 네트워크 연결을 통해 서버에 저장됩니다.",
            "embedding_vector": "[1.0,0.0]",
        },
        {
            "chunk_id": "answer",
            "document_id": "doc-2",
            "source_type": "hoyoverse_qna_onlygenshin",
            "category": "account",
            "title": "게임 진행도는 어떻게 초기화할 수 있나요?",
            "chunk_text": "로그인 화면 오른쪽 하단에서 로그아웃을 선택한 뒤 새로운 계정으로 로그인하면 새 게임을 시작할 수 있습니다.",
            "embedding_vector": "[0.98,0.02]",
        },
    ]

    results = hybrid_rank_documents(
        query_vector=[1.0, 0.0],
        query_text="게임 진행도 초기화 방법",
        rows=rows,
        top_k=2,
    )

    assert results[0]["chunk_id"] == "answer"
    assert results[0]["field_match_score"] > results[1]["field_match_score"]


def test_fetch_candidate_rows_broad_mode_orders_faq_sources_by_priority(monkeypatch) -> None:
    captured_sql = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params):
            captured_sql["sql"] = sql
            captured_sql["params"] = params

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, row_factory=None):
            return FakeCursor()

    monkeypatch.setattr(vector_tools, "db_connection", lambda: FakeConnection())

    vector_tools._fetch_candidate_rows(
        retrieval_query="게임 진행도 초기화",
        candidate_limit=10,
        faq_only=True,
        enrichment=None,
        use_query_filter=False,
    )

    sql = captured_sql["sql"]
    assert "hoyoverse_qna_onlygenshin" in sql
    assert "hoyoverse_qna_common" in sql
    assert "ORDER BY CASE" in sql


def _base_state() -> dict:
    return {
        "ticket_id": 1,
        "draft_text": "draft answer",
        "reasoning_node": "faq_agent",
        "category": "FAQ",
        "routing_target": "rag_reply",
    }


def test_draft_persistence_saves_retrieved_documents_as_evidence(monkeypatch) -> None:
    evidence_payloads = []

    monkeypatch.setattr(persistence, "_write_answer_draft", lambda payload: json.dumps({"draft_id": 10}))
    monkeypatch.setattr(persistence, "_write_evidence_doc", lambda payload: evidence_payloads.append(payload) or "{}")

    state = {
        **_base_state(),
        "retrieved_documents": [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "source_type": "hoyoverse_qna_common",
                "chunk_text": "first evidence",
                "score": 0.05,
            },
            {
                "chunk_id": "chunk-2",
                "document_id": "doc-2",
                "source_type": "naver_cafe_notice",
                "chunk_text": "second evidence",
                "score": 0.03,
            },
        ],
    }

    result = persistence.draft_persistence_node(state)

    assert result == {"draft_id": 10, "evidence_count": 2}
    assert evidence_payloads[0]["source_id"] == "chunk-1"
    assert evidence_payloads[0]["source_type"] == "hoyoverse_qna_common"
    assert evidence_payloads[0]["evidence_text"] == "first evidence"
    assert evidence_payloads[0]["retrieval_rank"] == 1
    assert evidence_payloads[1]["source_id"] == "chunk-2"


def test_draft_persistence_falls_back_to_draft_evidence(monkeypatch) -> None:
    evidence_payloads = []

    monkeypatch.setattr(persistence, "_write_answer_draft", lambda payload: json.dumps({"draft_id": 11}))
    monkeypatch.setattr(persistence, "_write_evidence_doc", lambda payload: evidence_payloads.append(payload) or "{}")

    result = persistence.draft_persistence_node(_base_state())

    assert result == {"draft_id": 11, "evidence_count": 1}
    assert evidence_payloads == [
        {
            "draft_id": 11,
            "source_type": "agent",
            "source_id": "faq_agent_generated_draft",
            "evidence_text": "draft answer",
            "relevance_score": 1.0,
            "retrieval_rank": 1,
        }
    ]
