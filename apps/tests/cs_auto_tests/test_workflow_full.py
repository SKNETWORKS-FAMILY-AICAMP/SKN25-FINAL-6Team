"""Full-path tests for the 6-step operation workflow graph."""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "apps" / "cs_auto" / "backend"
COMMON_ROOT = REPO_ROOT / "packages" / "common-python" / "src"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(COMMON_ROOT))

from workflow import build_operation_graph, nodes
from workflow.agents import ContextAgentResult
from workflow.prompts import DraftingAgentResponse, HumanReviewResponse, IntakeAgentResponse, ReviewAgentResponse
from workflow.state import AnalysisResult, EvidenceDocument, OperationState, SafetyResult


class FakeWorkflowDatabase:
    def __init__(self) -> None:
        self.ticket_status = "pending"
        self.executed_sql: list[str] = []
        self.sequences = {
            "ticket_analysis": 0,
            "answer_draft": 0,
            "evidence_docs": 0,
            "safety_results": 0,
            "final_response": 0,
            "notification_logs": 0,
        }
        self.inserted = {key: [] for key in self.sequences}

    def next_id(self, table_name: str) -> int:
        self.sequences[table_name] += 1
        return self.sequences[table_name]


class FakeCursor:
    def __init__(self, database: FakeWorkflowDatabase) -> None:
        self.database = database
        self.result: object = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        normalized_sql = " ".join(sql.lower().split())
        params = params or ()
        self.database.executed_sql.append(normalized_sql)

        if normalized_sql.startswith("insert into ticket_analysis"):
            self.database.inserted["ticket_analysis"].append(params)
            self.result = (self.database.next_id("ticket_analysis"),)
        elif normalized_sql.startswith("insert into answer_draft"):
            self.database.inserted["answer_draft"].append(params)
            self.result = (self.database.next_id("answer_draft"),)
        elif normalized_sql.startswith("insert into evidence_docs"):
            self.database.inserted["evidence_docs"].append(params)
            self.result = (self.database.next_id("evidence_docs"),)
        elif normalized_sql.startswith("insert into safety_results"):
            self.database.inserted["safety_results"].append(params)
            self.result = (self.database.next_id("safety_results"),)
        elif normalized_sql.startswith("insert into final_response"):
            self.database.inserted["final_response"].append(params)
            self.result = (self.database.next_id("final_response"),)
        elif normalized_sql.startswith("insert into notification_logs"):
            self.database.inserted["notification_logs"].append(params)
            self.result = (self.database.next_id("notification_logs"),)
        elif normalized_sql.startswith("update qa_ticket"):
            self.database.ticket_status = str(params[0])
            self.result = None
        else:
            raise AssertionError(f"Unhandled SQL in full workflow test: {normalized_sql}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result if isinstance(self.result, list) else []


class FakeConnection:
    def __init__(self, database: FakeWorkflowDatabase) -> None:
        self.database = database

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return FakeCursor(self.database)


def fake_db_connection(database: FakeWorkflowDatabase):
    @contextmanager
    def connection():
        yield FakeConnection(database)

    return connection


def happy_intake() -> IntakeAgentResponse:
    return IntakeAgentResponse(
        query_route="payment",
        route_reason="결제 관련 문의",
        target_route="rag_reply",
        risk_level="low",
        risk_reason="일반 결제 확인",
        summary="결제 상태 확인 요청",
        required_actions=["결제 이력 확인"],
        review_required=False,
        review_reason=None,
        required_context_types=["payment"],
    )


class WorkflowFullPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ticket_row = {
            "ticket_id": 1001,
            "user_id": 1,
            "account_id": 101,
            "title": "결제 확인",
            "raw_query": "결제 상품이 정상 반영됐는지 확인해주세요.",
            "source_type": "naver_cafe",
            "responder_type": "bot",
            "status": "pending",
            "inquiry_created_at": "2026-05-11 10:00:00",
        }

    def test_full_graph_happy_path_persists_expected_tables(self) -> None:
        database = FakeWorkflowDatabase()
        graph = build_operation_graph()
        context_result = ContextAgentResult(
            context={"payment": [{"payment_id": 11}]},
            context_nodes=["payment_context"],
            retrieved_docs=[
                EvidenceDocument(doc_id="chunk-1", source="policy", content="결제 안내", score=0.75),
                EvidenceDocument(doc_id="chunk-2", source="policy", content="환불 안내", score=0.60),
            ],
            evidence_doc_ids=["chunk-1", "chunk-2"],
        )
        drafting_response = DraftingAgentResponse(
            customer_answer="결제 내역과 지급 상태를 확인했습니다.",
            evidence_doc_ids=["chunk-1"],
        )
        review_response = ReviewAgentResponse(
            approval_route="approved",
            approved=True,
            evidence_matched=True,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=[],
        )
        human_review_response = HumanReviewResponse(decision="approved", reason="검토 완료", edited_answer=None)

        with patch.object(nodes, "_fetch_ticket", return_value=self.ticket_row):
            with patch.object(nodes, "db_connection", fake_db_connection(database)):
                with patch.object(nodes, "run_intake_agent", return_value=happy_intake()):
                    with patch.object(nodes, "run_context_agent", return_value=context_result):
                        with patch.object(nodes, "run_drafting_agent", return_value=drafting_response):
                            with patch.object(nodes, "run_review_agent", return_value=review_response):
                                with patch.object(nodes, "invoke_structured_llm", return_value=human_review_response):
                                    result = graph.invoke(OperationState(ticket_id="1001"))

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["final_answer"], "결제 내역과 지급 상태를 확인했습니다.")
        self.assertEqual(database.ticket_status, "closed")
        self.assertEqual(len(database.inserted["ticket_analysis"]), 1)
        self.assertEqual(len(database.inserted["answer_draft"]), 1)
        self.assertEqual(len(database.inserted["evidence_docs"]), 1)
        self.assertEqual(len(database.inserted["safety_results"]), 1)
        self.assertEqual(len(database.inserted["final_response"]), 1)

    def test_full_graph_urgent_path_writes_notification(self) -> None:
        database = FakeWorkflowDatabase()
        graph = build_operation_graph()
        context_result = ContextAgentResult(context={"payment": [{"payment_id": 11}]}, context_nodes=["payment_context"])
        drafting_response = DraftingAgentResponse(urgent_alert_message="긴급 결제 문의입니다. 운영자 확인이 필요합니다.")
        review_response = ReviewAgentResponse(
            approval_route="urgent_alert",
            approved=False,
            evidence_matched=False,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=["운영자 즉시 확인 필요"],
        )
        human_review_response = HumanReviewResponse(decision="approved", reason="긴급 알림 승인", edited_answer=None)

        with patch.object(nodes, "_fetch_ticket", return_value=self.ticket_row):
            with patch.object(nodes, "db_connection", fake_db_connection(database)):
                with patch.object(
                    nodes,
                    "run_intake_agent",
                    return_value=happy_intake().model_copy(update={"target_route": "urgent_alert", "risk_level": "critical"}),
                ):
                    with patch.object(nodes, "run_context_agent", return_value=context_result):
                        with patch.object(nodes, "run_drafting_agent", return_value=drafting_response):
                            with patch.object(nodes, "run_review_agent", return_value=review_response):
                                with patch.object(nodes, "invoke_structured_llm", return_value=human_review_response):
                                    result = graph.invoke(OperationState(ticket_id="1001"))

        self.assertEqual(result["status"], "urgent_alert_pending")
        self.assertEqual(database.ticket_status, "urgent_alert_pending")
        self.assertEqual(len(database.inserted["answer_draft"]), 1)
        self.assertEqual(len(database.inserted["notification_logs"]), 1)
        self.assertEqual(len(database.inserted["final_response"]), 0)


if __name__ == "__main__":
    unittest.main()
