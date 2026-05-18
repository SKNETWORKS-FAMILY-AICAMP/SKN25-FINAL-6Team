from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_core")

from chatbot.notifications.dispatcher import dispatch_urgent_alert
from chatbot.notifications.slack import send_slack_alert
from chatbot.observability.error_classifier import classify_error
from chatbot.observability.logger import EVENT_DB_WRITE_FAILED, build_log_event, log_event
from chatbot.response.final_response import final_response_node
from chatbot.tools.db_tools import read_payments, write_answer_draft, write_failed_query, write_voc_feedback


def _invoke(tool, payload: dict) -> dict:
    return json.loads(tool.invoke(payload))


def test_read_payments_uses_repository_response_contract() -> None:
    result = _invoke(read_payments, {"account_id": 101})

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["data"][0]["account_id"] == 101


def test_read_failure_returns_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "chatbot.repositories.operation_log_repository.settings",
        SimpleNamespace(use_seed_payload=False),
    )

    result = _invoke(read_payments, {"account_id": 101})

    assert result["status"] == "error"
    assert result["data"] == []
    assert result["count"] == 0
    assert result["error"] == "NotImplementedError"
    assert result["error_category"] == "not_implemented"


def test_write_voc_feedback_returns_topic_keywords() -> None:
    result = _invoke(
        write_voc_feedback,
        {
            "payload": {
                "ticket_id": 1005,
                "user_id": 1,
                "account_id": 101,
                "voc_type": "complaint",
                "sentiment": "negative",
                "raw_content": "이번 이벤트 보상이 너무 적어서 불만이에요.",
                "topic_keywords": ["이벤트", "보상", "불만"],
            },
        },
    )

    assert result["status"] == "ok"
    assert result["stored"] is True
    assert result["topic_keywords"] == ["이벤트", "보상", "불만"]


def test_write_failed_query_uses_repository_wrapper() -> None:
    result = _invoke(
        write_failed_query,
        {
            "payload": {
                "ticket_id": 1007,
                "query": "공월 축복이란 무엇인가요?",
                "category": "FAQ",
                "reason": "no reliable evidence",
            },
        },
    )

    assert result["status"] == "ok"
    assert result["ticket_id"] == 1007
    assert result["category"] == "FAQ"


def test_write_failure_returns_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "chatbot.repositories.draft_repository.settings",
        SimpleNamespace(use_seed_payload=False),
    )
    result = _invoke(write_answer_draft, {"payload": {"ticket_id": 9999, "content": "draft"}})

    assert result["status"] == "error"
    assert result["stored"] is False
    assert result["error"] == "NotImplementedError"
    assert result["error_category"] == "not_implemented"


def test_urgent_alert_dispatcher_returns_mock_without_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    result = dispatch_urgent_alert({
        "ticket_id": 1001,
        "session_id": "seed-session",
        "category": "결제",
        "routing_target": "urgent_alert",
        "raw_content": "결제했는데 아이템이 안 들어왔어요.",
        "final_answer": "담당자가 확인할 수 있도록 접수했습니다.",
    })

    assert result["status"] == "mock"


def test_urgent_alert_dispatcher_skips_non_urgent_target() -> None:
    result = dispatch_urgent_alert({
        "ticket_id": 1002,
        "session_id": "seed-session",
        "category": "FAQ",
        "routing_target": "rag_reply",
        "raw_content": "공월 축복이 뭐예요?",
    })

    assert result == {"status": "skipped", "reason": "routing_target is not urgent_alert"}


def test_slack_alert_failure_returns_classified_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("request timed out")

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setattr("chatbot.notifications.slack.request.urlopen", _raise_timeout)

    result = send_slack_alert("긴급 문의 테스트")

    assert result["status"] == "error"
    assert result["error"] == "TimeoutError"
    assert result["error_category"] == "timeout"


def test_final_response_dispatches_urgent_alert_without_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    result = final_response_node({
        "ticket_id": 1001,
        "session_id": "seed-session",
        "category": "결제",
        "routing_target": "urgent_alert",
        "raw_content": "결제했는데 아이템이 안 들어왔어요.",
        "answer_draft": "담당자가 확인할 수 있도록 접수했습니다.",
        "safety_action": "AUTO_RESPONSE",
    })

    assert result["final_answer"] == "담당자가 확인할 수 있도록 접수했습니다."
    assert result["notification_result"]["status"] == "mock"


def test_final_response_skips_notification_for_non_urgent_target() -> None:
    result = final_response_node({
        "ticket_id": 1002,
        "session_id": "seed-session",
        "category": "FAQ",
        "routing_target": "rag_reply",
        "raw_content": "공월 축복이 뭐예요?",
        "answer_draft": "공월 축복 안내입니다.",
        "safety_action": "AUTO_RESPONSE",
    })

    assert result["final_answer"] == "공월 축복 안내입니다."
    assert result["notification_result"]["status"] == "skipped"


def test_error_classifier_covers_common_infra_failures() -> None:
    assert classify_error(NotImplementedError("not ready")) == "not_implemented"
    assert classify_error(TimeoutError("request timed out")) == "timeout"
    assert classify_error(RuntimeError("could not connect to server: Connection refused")) == "connection_refused"
    assert classify_error(RuntimeError("password authentication failed for user")) == "auth_failed"
    assert classify_error(RuntimeError('relation "qa_ticket" does not exist')) == "schema_missing"
    assert classify_error(RuntimeError("duplicate key value violates unique constraint")) == "duplicate_key"


def test_log_event_prints_json_and_returns_event(capsys: pytest.CaptureFixture[str]) -> None:
    event = log_event(
        EVENT_DB_WRITE_FAILED,
        ticket_id=1001,
        session_id="seed-session",
        node_name="repository",
        category="결제",
        routing_target="urgent_alert",
        tool_name="write_answer_draft",
        status="error",
        error_message="forced failure",
        metadata={"error_type": "RuntimeError"},
    )

    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert printed == event
    assert printed["event_type"] == EVENT_DB_WRITE_FAILED
    assert printed["ticket_id"] == 1001
    assert printed["metadata"] == {"error_type": "RuntimeError"}


def test_build_log_event_adds_created_at() -> None:
    event = build_log_event(EVENT_DB_WRITE_FAILED, ticket_id=1001, status="error")

    assert event["event_type"] == EVENT_DB_WRITE_FAILED
    assert event["ticket_id"] == 1001
    assert event["status"] == "error"
    assert event["created_at"]
