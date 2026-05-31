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
            "category": "점검",
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
            "title": "왜 인터넷에 연결하여 게임을 플레이해야 하나요?",
            "chunk_text": "게임 진행도는 네트워크 연결을 통해 서버에 저장됩니다",
            "embedding_vector": "[1.0,0.0]",
        },
        {
            "chunk_id": "answer",
            "document_id": "doc-2",
            "source_type": "hoyoverse_qna_onlygenshin",
            "category": "account",
            "title": "게임 진행도는 어떻게 리셋할 수 있나요?",
            "chunk_text": "로그인 화면 오른쪽 하단에서 로그아웃을 선택하신 뒤 새로운 계정으로 로그인하면 새로운 게임을 시작할 수 있습니다",
            "embedding_vector": "[0.98,0.02]",
        },
    ]

    results = hybrid_rank_documents(
        query_vector=[1.0, 0.0],
        query_text="게임 진행도 리셋 방법",
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
        retrieval_query="게임 진행도 리셋",
        candidate_limit=10,
        faq_only=True,
        enrichment=None,
        use_query_filter=False,
    )

    sql = captured_sql["sql"]
    assert "hoyoverse_qna_onlygenshin" in sql
    assert "hoyoverse_qna_common" in sql
    assert "ORDER BY CASE" in sql
