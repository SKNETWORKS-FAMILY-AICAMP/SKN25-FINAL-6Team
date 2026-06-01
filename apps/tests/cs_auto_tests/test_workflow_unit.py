"""Unit tests for the 6-step operation workflow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "apps" / "cs_auto" / "backend"
COMMON_ROOT = REPO_ROOT / "packages" / "common-python" / "src"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(COMMON_ROOT))

from workflow import nodes
from workflow.agents import ContextAgentResult
from workflow.prompts import DraftingAgentResponse, HumanReviewResponse, IntakeAgentResponse, ReviewAgentResponse
from workflow.state import AnalysisResult, EvidenceDocument, OperationState


class LoadTicketTest(unittest.TestCase):
    def test_load_ticket_maps_database_row(self) -> None:
        row = {
            "ticket_id": 1001,
            "user_id": 1,
            "account_id": 101,
            "title": "결제 확인",
            "raw_query": "결제가 완료됐는지 확인해주세요.",
            "source_type": "naver_cafe",
            "responder_type": "bot",
            "status": "pending",
            "inquiry_created_at": "2026-05-11 10:00:00",
        }
        with patch.object(nodes, "_fetch_ticket", return_value=row):
            update = nodes.load_ticket(OperationState(ticket_id="1001"))
        self.assertEqual(update["ticket"].ticket_id, "1001")
        self.assertEqual(update["query_text"], "결제가 완료됐는지 확인해주세요.")


class IntakeAgentTest(unittest.TestCase):
    def test_intake_agent_sets_routing_and_analysis(self) -> None:
        response = IntakeAgentResponse(
            query_route="payment",
            route_reason="결제 관련 문의",
            target_route="rag_reply",
            risk_level="low",
            risk_reason="일반 문의",
            summary="결제 상태 확인 요청",
            required_actions=["결제 이력 확인"],
            review_required=False,
            review_reason=None,
            required_context_types=["payment"],
        )
        with patch.object(nodes, "run_intake_agent", return_value=response):
            update = nodes.intake_agent(OperationState(query_text="결제가 안 됐어요"))
        self.assertEqual(update["query_route"], "payment")
        self.assertEqual(update["target_route"], "rag_reply")
        self.assertEqual(update["analysis"].summary, "결제 상태 확인 요청")


class ContextAgentTest(unittest.TestCase):
    def test_context_agent_merges_context_and_retrieval(self) -> None:
        state = OperationState(
            ticket_id="1001",
            ticket=OperationState().ticket.model_copy(update={"user_id": "1", "metadata": {"account_id": 101}}),
            query_route="payment",
            target_route="rag_reply",
        )
        result = ContextAgentResult(
            context={"payment": [{"payment_id": 1}]},
            context_nodes=["payment_context"],
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1", source="policy", content="결제 안내", score=0.7)],
            evidence_doc_ids=["chunk-1"],
        )
        with patch.object(nodes, "_context_for_route", return_value=[{"payment_id": 1}]):
            with patch.object(nodes, "run_context_agent", return_value=result):
                update = nodes.context_agent(state)
        self.assertEqual(update["context_nodes"], ["payment_context"])
        self.assertEqual(update["evidence_doc_ids"], ["chunk-1"])


class DraftingAgentTest(unittest.TestCase):
    def test_drafting_agent_filters_unknown_evidence_ids(self) -> None:
        response = DraftingAgentResponse(
            customer_answer="결제 내역을 확인했습니다.",
            evidence_doc_ids=["chunk-1", "missing"],
        )
        state = OperationState(retrieved_docs=[EvidenceDocument(doc_id="chunk-1"), EvidenceDocument(doc_id="chunk-2")])
        with patch.object(nodes, "run_drafting_agent", return_value=response):
            update = nodes.drafting_agent(state)
        self.assertEqual(update["answer_draft"], "결제 내역을 확인했습니다.")
        self.assertEqual(update["evidence_doc_ids"], ["chunk-1"])


class ReviewAgentTest(unittest.TestCase):
    def test_review_agent_sets_approval_route(self) -> None:
        response = ReviewAgentResponse(
            approval_route="approved",
            approved=True,
            evidence_matched=True,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=[],
        )
        with patch.object(nodes, "run_review_agent", return_value=response):
            update = nodes.review_agent(OperationState(answer_draft="초안"))
        self.assertEqual(update["approval_route"], "approved")
        self.assertTrue(update["safety_result"].approved)


class ReviewStepTest(unittest.TestCase):
    def test_review_step_edit_sets_edited_answer(self) -> None:
        response = HumanReviewResponse(decision="edit", reason="문구 수정", edited_answer="수정된 답변")
        with patch.object(nodes, "invoke_structured_llm", return_value=response):
            update = nodes.review(OperationState(answer_draft="초안", approval_route="human_review"))
        self.assertEqual(update["human_decision"], "edit")
        self.assertEqual(update["edited_answer"], "수정된 답변")

    def test_review_step_regenerate_clears_downstream_fields(self) -> None:
        response = HumanReviewResponse(decision="regenerate", reason="검색 근거 부족", edited_answer=None)
        state = OperationState(
            answer_draft="초안",
            urgent_draft="긴급 초안",
            evidence_doc_ids=["chunk-1"],
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1")],
            approval_route="human_review",
        )
        with patch.object(nodes, "invoke_structured_llm", return_value=response):
            update = nodes.review(state)
        self.assertEqual(update["human_decision"], "regenerate")
        self.assertEqual(update["metadata"]["regenerate_reason"], "검색 근거 부족")
        self.assertEqual(update["evidence_doc_ids"], [])
        self.assertIsNone(update["answer_draft"])


class FinalizeTest(unittest.TestCase):
    def test_finalize_human_review_pending(self) -> None:
        state = OperationState(
            ticket_id="1001",
            approval_route="human_review",
            analysis=AnalysisResult(query_route="payment", target_route="rag_reply", risk_level="low", summary="요약"),
            answer_draft="초안",
            safety_result=OperationState().safety_result.model_copy(update={"approved": False, "evidence_matched": True}),
        )
        with patch.object(nodes, "_insert_analysis", return_value=1):
            with patch.object(nodes, "_insert_draft", return_value=2):
                with patch.object(nodes, "_insert_evidence_docs", return_value=None):
                    with patch.object(nodes, "_insert_safety_result", return_value=3):
                        with patch.object(nodes, "_update_ticket_status", return_value=None):
                            update = nodes.finalize(state)
        self.assertEqual(update["status"], "human_review_pending")
        self.assertEqual(update["analysis_id"], 1)
        self.assertEqual(update["draft_id"], 2)
        self.assertEqual(update["safety_id"], 3)


if __name__ == "__main__":
    unittest.main()
