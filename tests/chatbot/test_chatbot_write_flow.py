from __future__ import annotations

import os
import time
import unittest
from typing import Any

from dotenv import load_dotenv

from src.common.db.connection import db_connection

from chatbot.repository.analysis_repository import save_ticket_analysis
from chatbot.repository.draft_repository import save_answer_draft, save_evidence_docs
from chatbot.repository.failed_query_repository import save_failed_query
from chatbot.repository.final_response_repository import save_final_response
from chatbot.repository.safety_repository import save_safety_results
from chatbot.repository.ticket_repository import save_qa_ticket


load_dotenv()


class TestChatbotWriteFlow(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("DB_PASSWORD"):
            self.skipTest("DB_PASSWORD environment variable is required")

        self.ticket_ids: list[int] = []
        self.user_id, self.account_id = self._read_mock_account_or_skip()

    def tearDown(self) -> None:
        for ticket_id in self.ticket_ids:
            self._cleanup_ticket(ticket_id)

    def _skip_if_write_error(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("status") == "error":
            self.skipTest(f"Database write is not available: {result.get('error')}")
        return result

    def _read_mock_account_or_skip(self) -> tuple[int, int]:
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT cu.user_id, ga.account_id
                        FROM public.community_users cu
                        JOIN public.game_accounts ga
                          ON ga.user_id = cu.user_id
                        WHERE cu.user_status = 'active'
                          AND ga.account_status = 'active'
                        ORDER BY cu.user_id, ga.account_id
                        LIMIT 1
                        """
                    )
                    row = cur.fetchone()
        except Exception as exc:
            self.skipTest(f"Database connection is not available: {type(exc).__name__}")

        if not row:
            self.skipTest("No active mock user and game account are available")
        return int(row[0]), int(row[1])

    def _next_test_ticket_id(self) -> int:
        return int(time.time() * 1000) % 1_000_000_000

    def _cleanup_ticket(self, ticket_id: int) -> None:
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.final_response WHERE ticket_id = %s", (ticket_id,))
                    cur.execute(
                        """
                        DELETE FROM public.safety_results
                        WHERE draft_id IN (
                            SELECT draft_id FROM public.answer_draft WHERE ticket_id = %s
                        )
                        """,
                        (ticket_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM public.evidence_docs
                        WHERE draft_id IN (
                            SELECT draft_id FROM public.answer_draft WHERE ticket_id = %s
                        )
                        """,
                        (ticket_id,),
                    )
                    cur.execute("DELETE FROM public.answer_draft WHERE ticket_id = %s", (ticket_id,))
                    cur.execute("DELETE FROM public.failed_queries WHERE ticket_id = %s", (ticket_id,))
                    cur.execute("DELETE FROM public.ticket_analysis WHERE ticket_id = %s", (ticket_id,))
                    cur.execute("DELETE FROM public.qa_ticket WHERE ticket_id = %s", (ticket_id,))
        except Exception:
            # Cleanup is best-effort; test assertions should report the original failure.
            pass

    def _write_test_ticket(self, *, raw_query: str) -> int:
        ticket_id = self._next_test_ticket_id()
        self.ticket_ids.append(ticket_id)
        ticket_result = self._skip_if_write_error(
            save_qa_ticket(
                {
                    "ticket_id": ticket_id,
                    "user_id": self.user_id,
                    "account_id": self.account_id,
                    "session_id": None,
                    "title": "chatbot write flow test",
                    "raw_query": raw_query,
                    "source_type": "manual_test",
                    "status": "open",
                }
            )
        )
        self.assertTrue(ticket_result["stored"])
        self.assertEqual(ticket_id, int(ticket_result["ticket_id"]))
        return ticket_id

    def test_customer_response_write_flow_returns_database_generated_ids(self) -> None:
        ticket_id = self._write_test_ticket(raw_query="A 담당 DB write flow 테스트입니다.")

        analysis_result = self._skip_if_write_error(
            save_ticket_analysis(
                {
                    "ticket_id": ticket_id,
                    "category": "FAQ",
                    "responder_type": "AI",
                    "enriched_query": "DB write flow test",
                    "risk_level": "low",
                    "sentiment": "neutral",
                    "routing_target": "rag_reply",
                    "summary": "write flow integration test",
                }
            )
        )
        analysis_id = analysis_result["analysis_id"]

        draft_result = self._skip_if_write_error(
            save_answer_draft(
                {
                    "ticket_id": ticket_id,
                    "analysis_id": analysis_id,
                    "draft_text": "테스트 답변 초안입니다.",
                    "prompt_version": "test-write-flow",
                }
            )
        )
        draft_id = draft_result["draft_id"]

        evidence_result = self._skip_if_write_error(
            save_evidence_docs(
                {
                    "draft_id": draft_id,
                    "source_type": "manual_test",
                    "source_id": "test-doc-1",
                    "evidence_text": "테스트 근거 문서입니다.",
                    "relevance_score": 0.99,
                    "retrieval_rank": 1,
                }
            )
        )

        safety_result = self._skip_if_write_error(
            save_safety_results(
                {
                    "draft_id": draft_id,
                    "hallucination_score": 0.0,
                    "toxicity_score": 0.0,
                    "policy_violation_score": 0.0,
                    "factuality_score": 1.0,
                    "safety_action": "AUTO_RESPONSE",
                    "safety_reason": "test passed",
                    "retry_count": 0,
                }
            )
        )

        final_result = self._skip_if_write_error(
            save_final_response(
                {
                    "ticket_id": ticket_id,
                    "draft_id": draft_id,
                    "final_text": "테스트 최종 답변입니다.",
                    "safety_action": "AUTO_RESPONSE",
                }
            )
        )

        self.assertIsInstance(analysis_id, int)
        self.assertIsInstance(draft_id, int)
        self.assertIsInstance(evidence_result["evidence_id"], int)
        self.assertIsInstance(safety_result["safety_id"], int)
        self.assertIsInstance(final_result["response_id"], int)
        self.assertEqual(analysis_id, draft_result["analysis_id"])
        self.assertEqual(draft_id, evidence_result["draft_id"])
        self.assertEqual(draft_id, safety_result["draft_id"])
        self.assertEqual(draft_id, final_result["draft_id"])

    def test_failed_query_write_returns_database_generated_id(self) -> None:
        ticket_id = self._write_test_ticket(raw_query="검색 결과가 없는 테스트 질문입니다.")

        failed_result = self._skip_if_write_error(
            save_failed_query(
                {
                    "ticket_id": ticket_id,
                    "query": "검색 결과가 없는 테스트 질문입니다.",
                    "category": "FAQ",
                    "reason": "no_retrieved_documents",
                }
            )
        )

        self.assertTrue(failed_result["stored"])
        self.assertIsInstance(failed_result["failed_query_id"], int)
        self.assertEqual(ticket_id, failed_result["ticket_id"])
        self.assertEqual("FAQ", failed_result["category"])


if __name__ == "__main__":
    unittest.main()
