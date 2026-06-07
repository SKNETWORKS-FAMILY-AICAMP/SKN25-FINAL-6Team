from __future__ import annotations

from agents import analysis_agent, answer_agent, retrieval


def test_analysis_to_retrieval_to_answer_integration(monkeypatch) -> None:
    ticket = {
        "ticket_id": 9,
        "account_id": 90,
        "user_id": 900,
        "title": "결제 상품 미지급",
        "raw_query": "결제했는데 상품이 지급되지 않았습니다.",
        "source_type": "naver_cafe",
        "responder_type": "agent",
    }
    analysis = analysis_agent.analyze_ticket(ticket)

    class FakeOperationRetriever:
        def run_fixed_sql_lookup(self, ticket_payload, analysis_payload):
            return {
                "payments": [{"payment_id": 1, "payment_status": "paid"}],
                "refunds": [],
                "item_delivery_logs": [],
                "gacha_logs": [],
            }

        def detect_payment_delivery_gap(self, operation_logs):
            return {"has_gap": True, "payment_ids": ["1"], "review_required": True}

        def format_db_evidence(self, query_plan, rows):
            return [
                {
                    "source_type": rows[0]["_source_type"],
                    "source_id": rows[0].get("gap_payment_ids"),
                    "evidence_text": "paid payment has no delivery",
                    "relevance_score": 0.7,
                    "retrieval_rank": 1,
                }
            ]

    class FakeDocumentRetriever:
        def search_hybrid_documents(self, query, category=None, source_type=None, limit=None):
            return [
                {
                    "source_type": "faq",
                    "chunk_id": "faq-1",
                    "title": "지급 안내",
                    "chunk_text": "결제 후 미지급 시 운영 기록 확인",
                    "relevance_score": 0.8,
                    "retrieval_rank": 1,
                }
            ]

        def format_document_evidence(self, rows):
            return [
                {
                    "source_type": "faq",
                    "source_id": rows[0]["chunk_id"],
                    "evidence_text": rows[0]["chunk_text"],
                    "relevance_score": rows[0]["relevance_score"],
                    "retrieval_rank": rows[0]["retrieval_rank"],
                }
            ]

    router = retrieval.RetrievalRouter()
    router.operation_retriever = FakeOperationRetriever()
    router.document_retriever = FakeDocumentRetriever()
    monkeypatch.setattr(answer_agent, "RetrievalRouter", lambda: router)

    evidence = answer_agent.collect_answer_evidence(ticket, analysis, answer_agent.select_retrieval_strategy(analysis))
    draft = answer_agent.generate_answer_draft_text(ticket, analysis, evidence)
    safety = answer_agent.evaluate_answer_safety({"ticket_id": ticket["ticket_id"]}, evidence)

    assert analysis["routing_target"] == "DB&DOC"
    assert [item["source_type"] for item in evidence] == ["operation_gap", "faq"]
    assert "paid payment has no delivery" in draft
    assert safety["safety_action"] == "ready_for_review"

