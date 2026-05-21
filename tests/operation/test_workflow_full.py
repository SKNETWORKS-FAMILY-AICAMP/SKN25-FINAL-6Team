"""Full-path test for the operation workflow graph with fake DB and LLM."""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.operation.workflow import build_operation_graph
from src.operation.workflow import nodes
from src.operation.workflow.prompts import (
    AnswerDraftResponse,
    QueryRoutingResponse,
    SafetyReviewResponse,
    TicketAnalysisResponse,
    UrgentDraftResponse,
)
from src.operation.workflow.state import OperationState


class FakeWorkflowDatabase:
    def __init__(self) -> None:
        self.ticket_status = "pending"
        self.executed_sql: list[str] = []
        self.sequences: dict[str, int] = {
            "ticket_analysis": 0,
            "answer_draft": 0,
            "evidence_docs": 0,
            "safety_results": 0,
            "final_response": 0,
            "notification_logs": 0,
        }
        self.inserted: dict[str, list[tuple[object, ...]]] = {
            "ticket_analysis": [],
            "answer_draft": [],
            "evidence_docs": [],
            "safety_results": [],
            "final_response": [],
            "notification_logs": [],
        }

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

        if "from qa_ticket t" in normalized_sql:
            self.result = {
                "ticket_id": 1001,
                "user_id": 1,
                "account_id": 101,
                "title": "결제 확인",
                "raw_query": "결제 상품이 계정에 반영되었는지 확인해주세요.",
                "source_type": "naver_cafe",
                "status": self.database.ticket_status,
                "inquiry_created_at": "2026-05-11 10:00:00",
                "session_id": None,
                "email": "user1@game.com",
                "nickname": "원신 중수",
                "user_status": "active",
                "game_name": None,
                "uid": None,
                "server_region": None,
                "progression_level": None,
                "account_status": None,
            }
        elif "from payments p" in normalized_sql:
            self.result = [
                {
                    "payment_id": 11,
                    "account_id": 101,
                    "product_name": "월정액",
                    "payment_status": "paid",
                    "amount": 9900,
                }
            ]
        elif "from documents_chunks c" in normalized_sql:
            self.result = [
                {
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "source_type": "policy",
                    "category": "payment",
                    "title": "결제 안내",
                    "chunk_text": "결제 완료 후 아이템 지급 상태를 확인합니다.",
                    "score": 0.75,
                }
            ]
        elif normalized_sql.startswith("insert into ticket_analysis"):
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


def fake_structured_llm(*, system_prompt, user_prompt, response_model):
    if response_model is QueryRoutingResponse:
        return QueryRoutingResponse(query_route="payment", route_reason="결제 상태 확인")
    if response_model is TicketAnalysisResponse:
        return TicketAnalysisResponse(
            query_route="payment",
            target_route="rag_reply",
            risk_level="low",
            risk_reason="일반 결제 확인",
            summary="결제 상품 반영 확인 요청",
            required_actions=["결제 이력 확인", "지급 상태 확인"],
        )
    if response_model is AnswerDraftResponse:
        return AnswerDraftResponse(
            answer_draft="결제 내역과 지급 상태를 확인했습니다.",
            evidence_doc_ids=["chunk-1"],
        )
    if response_model is SafetyReviewResponse:
        return SafetyReviewResponse(
            approved=True,
            evidence_matched=True,
            hallucination_detected=False,
            policy_violation_detected=False,
            unsafe_expression_detected=False,
            reasons=[],
        )
    raise AssertionError(f"unexpected response model: {response_model}")


def fake_urgent_structured_llm(*, system_prompt, user_prompt, response_model):
    if response_model is QueryRoutingResponse:
        return QueryRoutingResponse(query_route="payment", route_reason="결제 위험 확인")
    if response_model is TicketAnalysisResponse:
        return TicketAnalysisResponse(
            query_route="payment",
            target_route="urgent_alert",
            risk_level="critical",
            risk_reason="운영자 즉시 확인 필요",
            summary="고위험 결제 문의",
            required_actions=["운영자 확인"],
        )
    if response_model is UrgentDraftResponse:
        return UrgentDraftResponse(urgent_draft="긴급 결제 문의입니다. 운영자 확인이 필요합니다.")
    raise AssertionError(f"unexpected response model: {response_model}")


class WorkflowFullPathTest(unittest.TestCase):
    def test_full_graph_happy_path_persists_expected_tables(self) -> None:
        database = FakeWorkflowDatabase()
        graph = build_operation_graph()

        with patch.object(nodes, "db_connection", fake_db_connection(database)):
            with patch.object(nodes, "invoke_structured_llm", fake_structured_llm):
                result = graph.invoke(OperationState(ticket_id="1001"))

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["final_answer"], "결제 내역과 지급 상태를 확인했습니다.")
        self.assertEqual(database.ticket_status, "closed")
        self.assertEqual(len(database.inserted["ticket_analysis"]), 1)
        self.assertEqual(len(database.inserted["answer_draft"]), 1)
        self.assertEqual(len(database.inserted["evidence_docs"]), 1)
        self.assertEqual(len(database.inserted["safety_results"]), 1)
        self.assertEqual(len(database.inserted["final_response"]), 1)
        self.assertEqual(database.inserted["final_response"][0][0], "1001")

    def test_full_graph_urgent_path_writes_notification_without_safety_publish(self) -> None:
        database = FakeWorkflowDatabase()
        graph = build_operation_graph()

        with patch.object(nodes, "db_connection", fake_db_connection(database)):
            with patch.object(nodes, "invoke_structured_llm", fake_urgent_structured_llm):
                result = graph.invoke(OperationState(ticket_id="1001"))

        self.assertEqual(result["status"], "urgent_alert_pending")
        self.assertEqual(database.ticket_status, "pending")
        self.assertEqual(len(database.inserted["answer_draft"]), 1)
        self.assertEqual(len(database.inserted["notification_logs"]), 1)
        self.assertEqual(len(database.inserted["safety_results"]), 0)
        self.assertEqual(len(database.inserted["final_response"]), 0)

    def test_full_graph_uses_returning_ids_without_max_id_queries(self) -> None:
        database = FakeWorkflowDatabase()
        graph = build_operation_graph()

        with patch.object(nodes, "db_connection", fake_db_connection(database)):
            with patch.object(nodes, "invoke_structured_llm", fake_structured_llm):
                first_result = graph.invoke(OperationState(ticket_id="1001"))
                second_result = graph.invoke(OperationState(ticket_id="1001"))

        self.assertEqual(first_result["analysis_id"], 1)
        self.assertEqual(second_result["analysis_id"], 2)
        self.assertEqual(first_result["draft_id"], 1)
        self.assertEqual(second_result["draft_id"], 2)
        self.assertFalse(any("select coalesce(max(" in sql for sql in database.executed_sql))


if __name__ == "__main__":
    unittest.main()
