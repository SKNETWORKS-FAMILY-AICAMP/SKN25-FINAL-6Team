from __future__ import annotations

from api import main


def test_cs_auto_api_contract_documents_answer_agent_integration() -> None:
    contract = main.get_cs_auto_api_contract()

    assert contract["regeneration_flow"] == "request_draft_regeneration -> regenerate_agent(ticket_id, regeneration_reason)"
    assert contract["regeneration_agent_function"] == "agents.answer_agent.regenerate_agent"
    assert contract["draft_update_policy"] == "overwrite_answer_draft_text"
    assert contract["approval_policy"] == "insert_final_response_then_resolve_ticket"
    assert contract["detail_payload_sections"] == ["ticket", "evidence", "safety", "history", "operationLogs"]
    assert contract["draft_update_side_effects"] == [
        "answer_draft.draft_text overwrite",
        "admin_event_logs event_type = draft_updated",
    ]
    assert contract["approval_side_effects"] == [
        "final_response insert",
        "qa_ticket.status = resolved",
        "admin_event_logs event_type = draft_approved",
    ]
    assert contract["frontend_detail_visibility"] == {
        "batch_draft_visible": True,
        "evidence_docs_visible": True,
        "safety_results_visible": True,
        "admin_history_visible": True,
        "operation_logs_visible": True,
    }


def test_frontend_ticket_payload_exposes_chatbot_pending_user_email() -> None:
    payload = main.build_frontend_ticket_payload(
        {
            "ticket_id": 1002,
            "draft_id": None,
            "response_id": None,
            "source_type": "chatbot",
            "status": "pending",
            "title": "챗봇 상담원 연결",
            "nickname": "user-a",
            "email": "user-a@example.com",
            "account_id": 102,
            "uid": None,
            "category": None,
            "risk_level": "LOW",
            "routing_target": "fixed_answer",
            "sentiment": "neutral",
            "summary": "",
            "raw_query": "상담원 연결 요청",
            "retry_count": 0,
        }
    )

    assert payload["sourceType"] == "chatbot"
    assert payload["rawStatus"] == "pending"
    assert payload["userEmail"] == "user-a@example.com"
    assert payload["email"] == "user-a@example.com"
    assert payload["draftId"] is None
    assert payload["draft"] == ""
