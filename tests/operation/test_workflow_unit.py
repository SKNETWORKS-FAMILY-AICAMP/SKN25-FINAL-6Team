"""Unit tests for individual operation workflow nodes and routers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.operation.workflow import nodes
from src.operation.workflow.prompts import (
    AnswerDraftResponse,
    HumanReviewResponse,
    QueryRoutingResponse,
    SafetyReviewResponse,
    TicketAnalysisResponse,
    UrgentDraftResponse,
)
from src.operation.workflow.state import EvidenceDocument, OperationState


def fake_structured_llm(*, system_prompt, user_prompt, response_model):
    if response_model is QueryRoutingResponse:
        return QueryRoutingResponse(query_route="payment", route_reason="결제 문의")
    if response_model is TicketAnalysisResponse:
        return TicketAnalysisResponse(
            query_route="payment",
            target_route="rag_reply",
            risk_level="low",
            risk_reason="긴급 위험 없음",
            summary="결제 상태 확인 요청",
            required_actions=["결제 이력 확인"],
        )
    if response_model is AnswerDraftResponse:
        return AnswerDraftResponse(answer_draft="결제 내역을 확인했습니다.", evidence_doc_ids=["chunk-1"])
    if response_model is UrgentDraftResponse:
        return UrgentDraftResponse(urgent_draft="운영자 확인이 필요합니다.")
    if response_model is SafetyReviewResponse:
        return SafetyReviewResponse(
            approved=True,
            evidence_matched=True,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=[],
        )
    if response_model is HumanReviewResponse:
        return HumanReviewResponse(decision="edit", reason="문구 보완", edited_answer="수정된 답변입니다.")
    raise AssertionError(f"unexpected response model: {response_model}")


class WorkflowUnitTest(unittest.TestCase):
    def test_load_ticket_maps_database_row_to_state_ticket(self) -> None:
        row = {
            "ticket_id": 1001,
            "user_id": 1,
            "account_id": 101,
            "title": "로그인 오류 문의",
            "raw_query": "로그인이 되지 않습니다.",
            "source_type": "naver_cafe",
            "status": "pending",
            "inquiry_created_at": "2026-05-11 10:00:00",
        }

        with patch.object(nodes, "_fetch_ticket", return_value=row):
            update = nodes.load_ticket(OperationState(ticket_id="1001"))

        self.assertEqual(update["ticket"].ticket_id, "1001")
        self.assertEqual(update["ticket"].metadata["account_id"], 101)
        self.assertEqual(update["query_text"], "로그인이 되지 않습니다.")

    def test_context_node_adds_route_context_and_node_name(self) -> None:
        state = OperationState(ticket_id="1001")
        state.ticket.user_id = "1"
        state.ticket.metadata = {"account_id": 101}

        with patch.object(nodes, "_context_for_route", return_value=[{"payment_id": 1, "amount": 9900}]):
            update = nodes.payment_context_node(state)

        self.assertEqual(update["context"]["payment"][0]["payment_id"], 1)
        self.assertEqual(update["context_nodes"], ["payment_context_node"])

    def test_llm_nodes_return_expected_state_updates(self) -> None:
        state = OperationState(
            ticket_id="1001",
            query_text="결제 내역 확인",
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1", content="결제 정책")],
        )

        with patch.object(nodes, "invoke_structured_llm", fake_structured_llm):
            route_update = nodes.query_router(state)
            analysis_update = nodes.analyze_ticket(state)
            answer_update = nodes.generate_answer_node(state)
            urgent_update = nodes.urgent_draft_node(state)
            safety_update = nodes.approval_gate_node(state)
            review_update = nodes.human_review_node(state)

        self.assertEqual(route_update["query_route"], "payment")
        self.assertEqual(analysis_update["target_route"], "rag_reply")
        self.assertEqual(answer_update["evidence_doc_ids"], ["chunk-1"])
        self.assertEqual(urgent_update["answer_draft"], "운영자 확인이 필요합니다.")
        self.assertEqual(safety_update["approval_route"], "approved")
        self.assertEqual(review_update["human_decision"], "edit")

    def test_router_functions_validate_required_state_values(self) -> None:
        with self.assertRaises(ValueError):
            nodes.route_by_query(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_target(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_approval(OperationState())
        with self.assertRaises(ValueError):
            nodes.route_by_human_decision(OperationState())

        state = OperationState(
            query_route="payment",
            target_route="rag_reply",
            approval_route="approved",
            human_decision="approved",
        )
        self.assertEqual(nodes.route_by_query(state), "payment")
        self.assertEqual(nodes.route_by_target(state), "rag_reply")
        self.assertEqual(nodes.route_by_approval(state), "approved")
        self.assertEqual(nodes.route_by_human_decision(state), "approved")

    def test_after_save_draft_routes_urgent_target_to_notification(self) -> None:
        urgent_state = OperationState(target_route="urgent_alert")
        evidence_state = OperationState(retrieved_docs=[EvidenceDocument(doc_id="chunk-1")])
        normal_state = OperationState()

        self.assertEqual(nodes.route_after_save_draft(urgent_state), "urgent_alert")
        self.assertEqual(nodes.route_after_save_draft(evidence_state), "save_evidence_docs")
        self.assertEqual(nodes.route_after_save_draft(normal_state), "approval_gate")


if __name__ == "__main__":
    unittest.main()
