from __future__ import annotations

import json

import pytest

from chatbot.chains.routing import route_after_draft_persistence, route_after_safety, route_by_category

from chatbot.constants import VOC_FIXED_RESPONSE
from chatbot.generation import ticket_preprocess, voc_agent
from chatbot.generation.response.ticket_completion import ticket_completion_node
from chatbot.generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    BUG_FALLBACK_RESPONSE,
    FAQ_FALLBACK_RESPONSE,
    PAYMENT_FALLBACK_RESPONSE,
    SAFE_FALLBACK_RESPONSE,
)
from chatbot.notifications import github_issue
from chatbot.observability.logger import log_event
from chatbot.safety import safety_layer
from chatbot.service.chatbot_service import build_state, last_message_text
from chatbot.utils.input_preprocessing import preprocess_user_input


def test_build_state_keeps_conversation_summary() -> None:
    state = build_state(
        ticket_id=1,
        user_message="게임 진행을 초기화하고 싶어요.",
        conversation_summary="이전 문의는 계정 진행도 초기화 관련 질문이었습니다.",
    )

    assert state["conversation_summary"] == "이전 문의는 계정 진행도 초기화 관련 질문이었습니다."


def test_preprocess_user_input_masks_sensitive_values_without_dropping_question() -> None:
    result = preprocess_user_input(
        "결제 문의입니다. email test@example.com phone 010-1234-5678 비밀번호: qwer1234"
    )

    assert result["raw_content"].startswith("결제 문의입니다.")
    assert "test@example.com" not in result["masked_content"]
    assert "010-1234-5678" not in result["masked_content"]
    assert "qwer1234" not in result["masked_content"]
    assert "결제 문의입니다." in result["masked_content"]
    assert result["masked"] is True
    assert result["detected_labels"] == ["email", "phone", "password"]


def test_build_state_uses_masked_content_for_runtime_message_but_keeps_raw_query() -> None:
    user_message = "아이템 미지급입니다. test@example.com 010-1234-5678"

    state = build_state(
        ticket_id=1,
        user_message=user_message,
        category="payment",
        ui_category="bug",
        sub_category="launch_access_error",
        routing_target="bug_agent",
    )

    assert state["raw_query"] == user_message
    assert state["masked_content"] != user_message
    assert "test@example.com" not in state["masked_content"]
    assert "010-1234-5678" not in state["messages"][-1]["content"]
    assert "Selected subcategory: launch_access_error" in state["messages"][-1]["content"]
    assert state["input_masked"] is True
    assert state["input_detected_labels"] == ["email", "phone"]


def test_ticket_preprocess_persists_raw_query_and_normalizes_masked_content(monkeypatch) -> None:
    saved_payloads = []

    class FakeWriteQaTicket:
        @staticmethod
        def invoke(args):
            saved_payloads.append(args["payload"])
            return {"stored": True}

    monkeypatch.setattr(ticket_preprocess, "write_qa_ticket", FakeWriteQaTicket)

    state = build_state(
        ticket_id=1,
        user_message="아이템 미지급입니다. test@example.com",
        category="faq",
        user_id=7,
        account_id=101,
    )
    update = ticket_preprocess.ticket_preprocess_node(state)

    assert saved_payloads[0]["raw_query"] == "아이템 미지급입니다. test@example.com"
    assert update["normalized_query"] == "아이템 미지급입니다. [EMAIL]"
    assert update["category"] == "faq"


def test_last_message_text_requires_final_text() -> None:
    with pytest.raises(RuntimeError, match="without final_text"):
        last_message_text({
            "draft_text": "draft should not be exposed",
            "messages": [{"role": "assistant", "content": "message should not be exposed"}],
        })


def test_last_message_text_returns_final_text() -> None:
    assert last_message_text({"final_text": "final answer", "draft_text": "draft"}) == "final answer"


def test_log_event_accepts_error_category_for_failed_operations() -> None:
    event = log_event(
        "db_write_failed",
        ticket_id=1,
        tool_name="write_answer_draft",
        status="error",
        error_message="not null violation",
        error_category="database_constraint",
    )

    assert event["error_category"] == "database_constraint"


def test_evidence_grounding_scores_use_retrieved_documents() -> None:
    documents = [
        {
            "title": "payment guide",
            "category": "payment",
            "chunk_text": "payment item delivery can be checked in logs",
        }
    ]

    factuality, hallucination, reason = safety_layer._evidence_grounding_scores(
        "payment item delivery checked in logs",
        documents,
    )

    assert factuality == 1.0
    assert hallucination == 0.0
    assert "evidence token coverage" in reason


def test_evidence_grounding_scores_penalize_nonfallback_without_evidence() -> None:
    factuality, hallucination, reason = safety_layer._evidence_grounding_scores(
        "This unsupported answer claims a specific policy.",
        [],
    )

    assert factuality == 0.0
    assert hallucination == 1.0
    assert reason == "no retrieved evidence for generated draft"


def test_evidence_grounding_scores_allow_safe_fallback_without_evidence() -> None:
    factuality, hallucination, reason = safety_layer._evidence_grounding_scores(
        SAFE_FALLBACK_RESPONSE,
        [],
    )

    assert factuality == 1.0
    assert hallucination == 0.0
    assert reason == "fallback response without retrieved evidence"


def test_safety_layer_stores_evidence_scores(monkeypatch) -> None:
    payloads = []

    monkeypatch.setattr(
        safety_layer,
        "_moderation_safety_check",
        lambda text: (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        ),
    )
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "payment item delivery checked in logs",
            "retrieved_documents": [
                {
                    "title": "payment guide",
                    "category": "payment",
                    "chunk_text": "payment item delivery can be checked in logs",
                }
            ],
            "retry_count": 0,
            "category": "FAQ",
            "routing_target": "rag_reply",
        }
    )

    assert update["safety_passed"] is True
    assert update["factuality_score"] == 1.0
    assert update["hallucination_score"] == 0.0
    assert payloads[0]["factuality_score"] == 1.0
    assert payloads[0]["hallucination_score"] == 0.0


def test_safety_action_blocks_moderation_flagged_content() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=True,
        scores={
            "toxicity_score": 0.9,
            "policy_violation_score": 0.9,
            "factuality_score": 1.0,
            "hallucination_score": 0.0,
        },
        draft_text="blocked content",
        documents=[{"chunk_text": "blocked content"}],
        state={},
    )

    assert safety_passed is False
    assert safety_action == "BLOCK_RESPONSE"
    assert review_required is False


def test_safety_action_uses_fallback_when_generated_without_evidence() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 0.0,
            "hallucination_score": 1.0,
        },
        draft_text="unsupported answer",
        documents=[],
        state={},
        requires_grounding=True,
    )

    assert safety_passed is False
    assert safety_action == "SAFE_FALLBACK"
    assert review_required is False


def test_safety_action_fallbacks_when_grounding_is_too_low() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 0.2,
            "hallucination_score": 0.8,
        },
        draft_text="partly unsupported answer",
        documents=[{"chunk_text": "some evidence"}],
        state={},
        requires_grounding=True,
    )

    assert safety_passed is False
    assert safety_action == "SAFE_FALLBACK"
    assert review_required is False


def test_safety_action_allows_middle_grounding_with_review_required() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 0.4,
            "hallucination_score": 0.6,
        },
        draft_text="partly paraphrased answer",
        documents=[{"chunk_text": "some evidence"}],
        state={},
        requires_grounding=True,
    )

    assert safety_passed is True
    assert safety_action == "AUTO_RESPONSE"
    assert review_required is True


def test_safety_action_auto_response_when_grounding_is_good() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 0.8,
            "hallucination_score": 0.3,
        },
        draft_text="grounded answer",
        documents=[{"chunk_text": "some evidence"}],
        state={},
        requires_grounding=True,
    )

    assert safety_passed is True
    assert safety_action == "AUTO_RESPONSE"
    assert review_required is False


def test_safety_layer_marks_faq_answer_with_medium_overlap_for_review(monkeypatch) -> None:
    payloads = []

    monkeypatch.setattr(
        safety_layer,
        "_moderation_safety_check",
        lambda text: (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        ),
    )
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "payment item delivery can be checked from purchase history and logs",
            "retrieved_documents": [{"chunk_text": "payment item delivery purchase history"}],
            "retry_count": 0,
            "category": "FAQ",
            "routing_target": "rag_reply",
            "reasoning_node": "faq_agent",
        }
    )

    assert update["safety_passed"] is True
    assert update["safety_action"] == "AUTO_RESPONSE"
    assert update["review_required"] is True
    assert payloads[0]["safety_action"] == "AUTO_RESPONSE"


def test_safety_action_allows_non_rag_agent_without_retrieved_documents() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 0.0,
            "hallucination_score": 1.0,
        },
        draft_text="결제 이력을 확인한 뒤 안내드리겠습니다.",
        documents=[],
        state={},
        requires_grounding=False,
    )

    assert safety_passed is True
    assert safety_action == "AUTO_RESPONSE"
    assert review_required is False


def test_safety_action_marks_received_bug_inquiry_for_review() -> None:
    safety_passed, safety_action, review_required = safety_layer._decide_safety_action(
        moderation_blocked=False,
        scores={
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": 1.0,
            "hallucination_score": 0.0,
        },
        draft_text=(
            "제공해주신 내용 기준으로 오류 문의가 접수되었습니다. "
            "현재 대화 내용만으로 원인을 확정하기는 어려워 로그 및 재현 조건 검토가 필요합니다."
        ),
        documents=[],
        state={"category": "bug", "reasoning_node": "bug_agent"},
        requires_grounding=False,
    )

    assert safety_passed is True
    assert safety_action == "REVIEW_REQUIRED"
    assert review_required is True


def test_safety_layer_does_not_fallback_payment_agent_without_rag_docs(monkeypatch) -> None:
    payloads = []

    monkeypatch.setattr(
        safety_layer,
        "_moderation_safety_check",
        lambda text: (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        ),
    )
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "갤럭시 스토어 결제 방법은 결제 화면에서 결제 수단을 선택해 진행할 수 있습니다.",
            "retrieved_documents": [],
            "retry_count": 0,
            "category": "결제",
            "routing_target": "urgent_alert",
            "reasoning_node": "payment_agent",
        }
    )

    assert update["safety_passed"] is True
    assert update["safety_action"] == "AUTO_RESPONSE"
    assert payloads[0]["safety_action"] == "AUTO_RESPONSE"


def test_safety_layer_does_not_ground_non_faq_payment_context_documents(monkeypatch) -> None:
    payloads = []

    monkeypatch.setattr(
        safety_layer,
        "_moderation_safety_check",
        lambda text: (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        ),
    )
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "결제 이력을 확인한 뒤 해당 아이템 지급 여부를 안내드리겠습니다.",
            "retrieved_documents": [
                {
                    "source_type": "payments",
                    "category": "결제",
                    "chunk_text": "payment_id=201 payment_status=paid amount=12000",
                }
            ],
            "retry_count": 0,
            "category": "결제",
            "routing_target": "urgent_alert",
            "reasoning_node": "payment_agent",
            "should_use_rag": False,
        }
    )

    assert update["safety_passed"] is True
    assert update["safety_action"] == "AUTO_RESPONSE"
    assert update["review_required"] is False
    assert payloads[0]["factuality_score"] == 1.0
    assert payloads[0]["hallucination_score"] == 0.0


def test_mask_sensitive_text_masks_common_private_values() -> None:
    masked_text, labels = safety_layer._mask_sensitive_text(
        "email test@example.com phone 010-1234-5678 account_id=abc12345"
    )

    assert "test@example.com" not in masked_text
    assert "010-1234-5678" not in masked_text
    assert "abc12345" not in masked_text
    assert set(labels) == {"email", "phone", "account_id"}


def test_safety_layer_masks_and_rechecks_only_masked_text(monkeypatch) -> None:
    payloads = []
    moderated_texts = []

    def fake_moderation(text):
        moderated_texts.append(text)
        return (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        )

    monkeypatch.setattr(safety_layer, "_moderation_safety_check", fake_moderation)
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "문의 결과를 test@example.com 으로 안내합니다.",
            "retrieved_documents": [{"chunk_text": "문의 결과는 이메일로 안내합니다."}],
            "retry_count": 0,
            "category": "FAQ",
            "routing_target": "rag_reply",
        }
    )

    assert update["safety_action"] == "MASKING"
    assert update["retry_count"] == 1
    assert update["masking_labels"] == ["email"]
    assert "test@example.com" not in update["draft_text"]
    assert "test@example.com" not in moderated_texts[0]
    assert payloads[0]["safety_action"] == "MASKING"


def test_safety_layer_fallbacks_after_masking_retry_exhausted(monkeypatch) -> None:
    payloads = []

    monkeypatch.setattr(
        safety_layer,
        "_moderation_safety_check",
        lambda text: (
            False,
            {"toxicity_score": 0.01, "policy_violation_score": 0.02},
            "moderation ok",
        ),
    )
    monkeypatch.setattr(safety_layer, "_write_safety_results", lambda payload: payloads.append(payload) or "{}")

    update = safety_layer.safety_layer_node(
        {
            "ticket_id": 1,
            "draft_id": 2,
            "draft_text": "문의 결과를 test@example.com 으로 안내합니다.",
            "retrieved_documents": [{"chunk_text": "문의 결과는 이메일로 안내합니다."}],
            "retry_count": 2,
            "category": "FAQ",
            "routing_target": "rag_reply",
        }
    )

    assert update["safety_action"] == "SAFE_FALLBACK"
    assert update["draft_text"] == SAFE_FALLBACK_RESPONSE
    assert update["retry_count"] == 3
    assert payloads[0]["safety_action"] == "SAFE_FALLBACK"


def _final_state(category: str, safety_action: str = "SAFE_FALLBACK") -> dict:
    return {
        "ticket_id": 1,
        "session_id": 1,
        "draft_id": 10,
        "draft_text": "draft",
        "category": category,
        "routing_target": "rag_reply",
        "safety_action": safety_action,
    }


def _patch_ticket_completion_writes(monkeypatch) -> dict[str, list[dict]]:
    payloads = {"ticket": []}

    def fake_update_raw_query(payload):
        payloads["ticket"].append(payload)
        return {"stored": True, "ticket_id": payload["ticket_id"]}

    monkeypatch.setattr(
        "chatbot.generation.response.ticket_completion.update_qa_ticket_raw_query",
        fake_update_raw_query,
    )
    monkeypatch.setattr(
        "chatbot.generation.response.ticket_completion.dispatch_github_issue_notification",
        lambda state: {"status": "skipped"},
    )
    return payloads


def test_ticket_completion_uses_category_fallbacks(monkeypatch) -> None:
    payloads = _patch_ticket_completion_writes(monkeypatch)

    cases = [
        ("결제", PAYMENT_FALLBACK_RESPONSE),
        ("인게임/버그", BUG_FALLBACK_RESPONSE),
        ("FAQ", FAQ_FALLBACK_RESPONSE),
        ("VOC", VOC_FIXED_RESPONSE),
    ]

    for category, expected in cases:
        result = ticket_completion_node(_final_state(category))
        assert result["final_text"] == expected

    assert [payload["raw_query"] for payload in payloads["ticket"]] == [
        f"User: \nAI: {expected}" for _, expected in cases
    ]


def test_ticket_completion_uses_fixed_block_and_review_responses(monkeypatch) -> None:
    payloads = _patch_ticket_completion_writes(monkeypatch)

    assert ticket_completion_node(_final_state("FAQ", "BLOCK_RESPONSE"))["final_text"] == BLOCK_RESPONSE
    assert ticket_completion_node(_final_state("FAQ", "REVIEW_REQUIRED"))["final_text"] == "draft"
    assert [payload["status"] for payload in payloads["ticket"]] == ["resolved", "pending"]


def test_ticket_completion_does_not_write_chatbot_insight(monkeypatch) -> None:
    _patch_ticket_completion_writes(monkeypatch)

    result = ticket_completion_node({
        **_final_state("payment"),
        "user_id": 1,
        "account_id": 101,
        "raw_query": "결제 문의입니다.",
    })

    assert "insight_result" not in result


def test_dispatch_github_issue_creates_issue_for_review_required_bug(monkeypatch) -> None:
    github_calls = []
    notification_logs = []

    monkeypatch.setattr(
        github_issue,
        "_create_github_issue",
        lambda title, body: github_calls.append((title, body))
        or {"status": "ok", "issue_url": "https://github.com/acme/game/issues/1"},
    )
    monkeypatch.setattr(github_issue, "notification_log_exists", lambda ticket_id, channel: {"exists": False})
    monkeypatch.setattr(
        github_issue,
        "save_notification_log",
        lambda payload: notification_logs.append(payload) or {"status": "ok", "stored": True},
    )
    monkeypatch.setattr(github_issue, "log_event", lambda *args, **kwargs: {})

    result = github_issue.dispatch_github_issue_notification(
        {
            "ticket_id": 1,
            "session_id": 2,
            "user_id": 3,
            "account_id": 4,
            "category": "bug",
            "routing_target": "urgent_alert",
            "reasoning_node": "bug_agent",
            "safety_action": "REVIEW_REQUIRED",
            "review_required": True,
            "normalized_query": "game closes after loading",
            "final_text": "operator will review",
        }
    )

    assert result["status"] == "ok"
    assert github_calls
    assert github_calls[0][0] == "[버그 검토 필요] game closes after loading"
    assert [payload["channel"] for payload in notification_logs] == ["github_issue"]


def test_dispatch_github_issue_skips_for_non_bug(monkeypatch) -> None:
    github_calls = []

    monkeypatch.setattr(
        github_issue,
        "_create_github_issue",
        lambda title, body: github_calls.append((title, body)) or {"status": "ok"},
    )
    monkeypatch.setattr(github_issue, "save_notification_log", lambda payload: {"status": "ok", "stored": True})
    monkeypatch.setattr(github_issue, "log_event", lambda *args, **kwargs: {})

    result = github_issue.dispatch_github_issue_notification(
        {
            "ticket_id": 1,
            "category": "payment",
            "routing_target": "urgent_alert",
            "reasoning_node": "payment_agent",
            "safety_action": "REVIEW_REQUIRED",
            "review_required": True,
            "normalized_query": "paid item was not delivered",
        }
    )

    assert result["status"] == "skipped"
    assert not github_calls


def test_dispatch_github_issue_skips_duplicate_ticket(monkeypatch) -> None:
    github_calls = []

    monkeypatch.setattr(
        github_issue,
        "_create_github_issue",
        lambda title, body: github_calls.append((title, body)) or {"status": "ok"},
    )
    monkeypatch.setattr(github_issue, "notification_log_exists", lambda ticket_id, channel: {"exists": True})
    monkeypatch.setattr(github_issue, "log_event", lambda *args, **kwargs: {})

    result = github_issue.dispatch_github_issue_notification(
        {
            "ticket_id": 1,
            "category": "bug",
            "routing_target": "urgent_alert",
            "reasoning_node": "bug_agent",
            "safety_action": "REVIEW_REQUIRED",
            "review_required": True,
            "normalized_query": "needs human review",
        }
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "github issue already created for ticket_id"
    assert not github_calls


def test_voc_agent_uses_fallback_for_non_actionable_non_rag_intent(monkeypatch) -> None:
    result = voc_agent.voc_agent_node(
        {
            "ticket_id": 1,
            "user_id": 1,
            "account_id": 101,
            "normalized_query": "게임 이용 불만",
            "routing_target": "rag_reply",
            "retry_count": 0,
            "is_actionable": False,
            "should_use_rag": False,
            "fallback_reason": "low_information_complaint",
        }
    )

    assert result["draft_text"] == VOC_FIXED_RESPONSE
    assert result["safety_action"] == "AUTO_RESPONSE"
    assert result["safety_reason"] == "VOC fixed response."

def test_route_by_user_selected_categories() -> None:
    assert route_by_category({"category": "payment"}) == "payment_agent"
    assert route_by_category({"category": "bug"}) == "bug_agent"
    assert route_by_category({"category": "faq"}) == "faq_agent"
    assert route_by_category({"category": "voc"}) == "voc_agent"

def test_voc_skips_safety_and_never_retries_from_safety() -> None:
    voc_state = {
        "category": "VOC",
        "reasoning_node": "voc_agent",
        "safety_passed": False,
        "safety_action": "AUTO_RESPONSE",
        "retry_count": 0,
    }

    assert route_after_draft_persistence(voc_state) == "ticket_completion"
    assert route_after_safety(voc_state) == "ticket_completion"


def test_route_after_draft_persistence_skips_safety_for_voc() -> None:
    assert route_after_draft_persistence({"category": "voc"}) == "ticket_completion"
    assert route_after_draft_persistence({"category": "faq"}) == "safety_layer"
