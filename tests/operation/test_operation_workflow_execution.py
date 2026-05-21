"""Execution checks for the operation workflow LLM path."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.common.db.connection import db_connection
from src.common.llm import client
from src.operation.workflow import build_operation_graph
from src.operation.workflow import nodes
from src.operation.workflow.prompts import QueryRoutingResponse
from src.operation.workflow.state import EvidenceDocument, OperationState


class FakeStructuredLlm:
    def __init__(self, response_model):
        self.response_model = response_model

    def invoke(self, messages):
        response_name = self.response_model.__name__
        if response_name == "QueryRoutingResponse":
            return self.response_model(query_route="payment", route_reason="payment inquiry")
        if response_name == "TicketAnalysisResponse":
            return self.response_model(
                query_route="payment",
                target_route="rag_reply",
                risk_level="low",
                risk_reason="no urgent risk",
                summary="payment status check",
                required_actions=["check payment history"],
            )
        if response_name == "AnswerDraftResponse":
            return self.response_model(answer_draft="결제 내역을 확인했습니다.", evidence_doc_ids=["chunk-1"])
        if response_name == "UrgentDraftResponse":
            return self.response_model(urgent_draft="운영자 확인이 필요합니다.")
        if response_name == "SafetyReviewResponse":
            return self.response_model(
                approved=True,
                evidence_matched=True,
                hallucination_detected=False,
                policy_violation_detected=False,
                unsafe_expression_detected=False,
                reasons=[],
            )
        if response_name == "HumanReviewResponse":
            return self.response_model(decision="approved", reason="safe to publish")
        raise AssertionError(f"Unexpected response model: {response_name}")


class FakeChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def with_structured_output(self, response_model):
        return FakeStructuredLlm(response_model)


class OperationWorkflowExecutionTest(unittest.TestCase):
    def test_llm_client_invokes_chat_openai_with_structured_output(self) -> None:
        with patch.dict(os.environ, {"LLM_MODEL": "test-model", "LLM_API_KEY": "test-key"}):
            with patch.object(client, "ChatOpenAI", FakeChatOpenAI):
                response = client.invoke_structured_llm(
                    system_prompt="system",
                    user_prompt="user",
                    response_model=QueryRoutingResponse,
                )

        self.assertEqual(response.query_route, "payment")
        self.assertEqual(response.route_reason, "payment inquiry")

    def test_operation_llm_nodes_execute_with_common_client_contract(self) -> None:
        def fake_invoke_structured_llm(*, system_prompt, user_prompt, response_model):
            return FakeStructuredLlm(response_model).invoke([])

        state = OperationState(
            ticket_id="1",
            query_text="결제 내역 확인 요청",
            retrieved_docs=[EvidenceDocument(doc_id="chunk-1", content="결제 정책 근거")],
            answer_draft="결제 내역을 확인했습니다.",
        )

        with patch.object(nodes, "invoke_structured_llm", fake_invoke_structured_llm):
            route_update = nodes.query_router(state)
            analysis_update = nodes.analyze_ticket(state)
            answer_update = nodes.generate_answer_node(state)
            urgent_update = nodes.urgent_draft_node(state)
            safety_update = nodes.approval_gate_node(state)
            review_update = nodes.human_review_node(state)

        self.assertEqual(route_update["query_route"], "payment")
        self.assertEqual(analysis_update["target_route"], "rag_reply")
        self.assertEqual(answer_update["evidence_doc_ids"], ["chunk-1"])
        self.assertIn("urgent_draft", urgent_update)
        self.assertEqual(safety_update["approval_route"], "approved")
        self.assertEqual(review_update["human_decision"], "approved")

    def test_operation_graph_compiles(self) -> None:
        graph = build_operation_graph()

        self.assertEqual(type(graph).__name__, "CompiledStateGraph")


class OperationWorkflowDatabaseWriteTest(unittest.TestCase):
    def test_database_write_is_available_inside_rollback_transaction(self) -> None:
        env = dotenv_values(REPO_ROOT / ".env")
        required_keys = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
        missing_keys = [key for key in required_keys if not env.get(key)]
        if missing_keys:
            self.skipTest(f"Missing DB environment keys: {', '.join(missing_keys)}")

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_event_logs (
                        node_name, event_type, status
                    )
                    VALUES (%s, %s, %s)
                    RETURNING log_id
                    """,
                    (
                        "operation_workflow_db_write_test",
                        "write_check",
                        "test",
                    ),
                )
                log_id = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM admin_event_logs WHERE log_id = %s", (log_id,))
                written_count = cur.fetchone()[0]
                conn.rollback()

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM admin_event_logs WHERE log_id = %s", (log_id,))
                persisted_count = cur.fetchone()[0]

        self.assertEqual(written_count, 1)
        self.assertEqual(persisted_count, 0)


if __name__ == "__main__":
    unittest.main()
