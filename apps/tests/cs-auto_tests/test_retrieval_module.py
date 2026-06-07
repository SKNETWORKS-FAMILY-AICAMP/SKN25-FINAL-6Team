from __future__ import annotations

from pathlib import Path

from agents import retrieval


def test_bm25_token_vector_and_cosine_helpers() -> None:
    assert retrieval._bm25_tokens("환불 결제 오류! refund_01") == ["환불", "결제", "오류", "refund_01"]
    assert retrieval._vector_literal([1, 0.5]) == "[1.0,0.5]"
    assert retrieval._parse_vector_literal("[1.0, 0.5]") == [1.0, 0.5]
    assert retrieval._cosine_similarity([1, 0], [1, 0]) == 1.0
    assert retrieval._cosine_similarity([1, 0], [0, 1]) == 0.0


def test_bm25_scores_rank_matching_chunk_higher() -> None:
    rows = [
        {"chunk_id": "refund", "title": "환불 결제", "category": "payment", "chunk_text": "결제 취소 환불 안내"},
        {"chunk_id": "login", "title": "로그인", "category": "account", "chunk_text": "비밀번호 재설정"},
    ]

    scores = retrieval._bm25_scores("환불 결제", rows)

    assert scores["refund"] > scores["login"]


def test_document_bm25_index_file_is_used(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(retrieval, "_BM25_INDEX_PATH", tmp_path / "cs_auto_bm25.pkl")

    class FakeRetriever(retrieval.DocumentRetriever):
        fetch_count = 0

        def _fetch_bm25_index_rows(self) -> list[dict[str, object]]:
            self.fetch_count += 1
            return [
                {"chunk_id": "a", "document_id": 1, "title": "환불 결제", "category": "payment", "chunk_text": "환불 안내"},
                {"chunk_id": "b", "document_id": 2, "title": "로그인", "category": "account", "chunk_text": "계정 복구"},
            ]

    retriever = FakeRetriever()
    first = retriever.search_bm25_documents("환불 결제", limit=1)
    second = retriever.search_bm25_documents("환불 결제", limit=1)

    assert retrieval._BM25_INDEX_PATH.exists()
    assert retriever.fetch_count == 1
    assert first[0]["chunk_id"] == "a"
    assert second[0]["bm25_index_path"] == str(retrieval._BM25_INDEX_PATH)


def test_dense_search_uses_pgvector_candidates_and_python_cosine(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "get_query_embedding", lambda query: [1.0, 0.0])

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return [
                {
                    "chunk_id": "near",
                    "document_id": 1,
                    "chunk_text": "near",
                    "chunk_order": 1,
                    "source_type": "faq",
                    "category": "payment",
                    "title": "near",
                    "embedding_vector": "[1.0,0.0]",
                    "cosine_score": 0.0,
                    "cosine_distance": 1.0,
                },
                {
                    "chunk_id": "far",
                    "document_id": 2,
                    "chunk_text": "far",
                    "chunk_order": 1,
                    "source_type": "faq",
                    "category": "payment",
                    "title": "far",
                    "embedding_vector": "[0.0,1.0]",
                    "cosine_score": 1.0,
                    "cosine_distance": 0.0,
                },
            ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(retrieval, "db_connection", lambda: FakeConnection())

    results = retrieval.DocumentRetriever().search_dense_documents("결제", limit=2)

    assert results[0]["chunk_id"] == "near"
    assert results[0]["cosine_score"] == 1.0
    assert results[1]["cosine_score"] == 0.0


def test_merge_and_rerank_documents_uses_rrf() -> None:
    retriever = retrieval.DocumentRetriever()
    dense = [
        {"chunk_id": "a", "dense_rank": 1, "dense_score": 0.9},
        {"chunk_id": "c", "dense_rank": 2, "dense_score": 0.8},
        {"chunk_id": "b", "dense_rank": 3, "dense_score": 0.7},
    ]
    bm25 = [{"chunk_id": "b", "bm25_rank": 1, "bm25_score": 3.0}, {"chunk_id": "a", "bm25_rank": 2, "bm25_score": 2.0}]

    results = retriever.merge_and_rerank_documents("query", dense, bm25)

    assert results[0]["chunk_id"] == "a"
    assert results[1]["chunk_id"] == "b"
    assert all("rrf_score" in row for row in results)


def test_format_document_evidence_limits_text() -> None:
    evidence = retrieval.DocumentRetriever().format_document_evidence(
        [{"source_type": "faq", "chunk_id": "c1", "title": "제목", "chunk_text": "본문", "relevance_score": 0.7}]
    )

    assert evidence == [
        {
            "source_type": "faq",
            "source_id": "c1",
            "evidence_text": "제목: 본문",
            "relevance_score": 0.7,
            "retrieval_rank": 1,
        }
    ]


def test_operation_log_gap_plan_execute_and_format(monkeypatch) -> None:
    retriever = retrieval.OperationLogRetriever()
    plan = retriever.build_text_to_sql_plan("환불과 뽑기 내역 확인", {"category": "refund", "account_id": 10})

    assert plan["tables"] == ["payments", "item_delivery_logs", "refunds", "gacha_logs"]

    monkeypatch.setattr(retriever, "fetch_payment_logs", lambda account_id: [{"payment_id": 1, "payment_status": "paid"}])
    monkeypatch.setattr(retriever, "fetch_item_delivery_logs", lambda account_id: [{"delivery_id": 3}])
    monkeypatch.setattr(retriever, "fetch_gacha_logs", lambda account_id: [{"gacha_id": 4}])
    rows = retriever.execute_text_to_sql({"account_id": 10, "tables": ["payments", "item_delivery_logs", "gacha_logs"]})

    assert [row["_source_type"] for row in rows] == ["payments", "item_delivery_logs", "gacha_logs"]
    assert retriever.detect_payment_delivery_gap({"payments": [{"payment_id": 1, "payment_status": "paid"}], "item_delivery_logs": []}) == {
        "has_gap": True,
        "payment_ids": ["1"],
        "review_required": True,
    }
    formatted = retriever.format_db_evidence({"source_type": "operation_db"}, rows[:1])
    assert formatted[0]["source_type"] == "payments"


def test_retrieval_router_routes_to_expected_method(monkeypatch) -> None:
    router = retrieval.RetrievalRouter()
    monkeypatch.setattr(router, "retrieve_db_only", lambda ticket, analysis: [{"source_type": "db"}])
    monkeypatch.setattr(router, "retrieve_doc_only", lambda ticket, analysis: [{"source_type": "doc"}])
    monkeypatch.setattr(router, "retrieve_fixed_answer_context", lambda ticket, analysis: [{"source_type": "fixed"}])

    ticket = {"ticket_id": 1}

    assert router.select_retrieval_functions({"routing_target": "DB&DOC"}) == ["retrieve_db_and_doc"]
    assert router.retrieve_by_routing_target(ticket, {"routing_target": "DB_only"}) == [{"source_type": "db"}]
    assert router.retrieve_by_routing_target(ticket, {"routing_target": "doc_only"}) == [{"source_type": "doc"}]
    assert router.retrieve_by_routing_target(ticket, {"routing_target": "fixed_answer"}) == [{"source_type": "fixed"}]
