from __future__ import annotations

import json

import pytest

from chatbot.chains.routing import route_by_category

from chatbot.constants import VOC_FIXED_RESPONSE
from chatbot.generation import ticket_preprocess, voc_agent
from chatbot.generation.response.final_response import final_response_node
from chatbot.generation.response.fixed_responses import (
    BLOCK_RESPONSE,
    BUG_FALLBACK_RESPONSE,
    FAQ_FALLBACK_RESPONSE,
    PAYMENT_FALLBACK_RESPONSE,
    REVIEW_QUEUE_RESPONSE,
    SAFE_FALLBACK_RESPONSE,
)
from chatbot.notifications import dispatcher
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

    state = build_state(ticket_id=1, user_message=user_message, category="payment")

    assert state["raw_query"] == user_message
    assert state["masked_content"] != user_message
    assert "test@example.com" not in state["masked_content"]
    assert "010-1234-5678" not in state["messages"][-1]["content"]
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
    assert update["enriched_query"] == "아이템 미지급입니다. [EMAIL]"
    assert update["query_enrichment_method"] == "normalize_only"
    assert update["query_enrichment_terms"] == []
    assert update["category"] == "faq"


def test_last_message_text_requires_final_text() -> None:
    with pytest.raises(RuntimeError, match="without final_text"):
        last_message_text({
            "draft_text": "draft should not be exposed",
            "messages": [{"role": "assistant", "content": "message should not be exposed"}],
        })


def test_last_message_text_returns_final_text() -> None:
    assert last_message_text({"final_text": "final answer", "draft_text": "draft"}) == "final answer"


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
        requires_grounding=False,
    )

    assert safety_passed is True
    assert safety_action == "AUTO_RESPONSE"
    assert review_required is False


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


def _patch_final_response_writes(monkeypatch) -> list[dict]:
    payloads = []

    class FakeWriteFinalResponse:
        @staticmethod
        def invoke(args):
            payloads.append(args["payload"])
            return json.dumps({"stored": True, "response_id": 123})

    class FakeUpdateTicketStatus:
        @staticmethod
        def invoke(args):
            return json.dumps({"stored": True, "ticket_status": args["payload"]["status"]})

    class FakeWriteInsight:
        @staticmethod
        def invoke(args):
            return json.dumps({"stored": True, "insight_id": 456})

    monkeypatch.setattr(
        "chatbot.generation.response.final_response.write_final_response",
        FakeWriteFinalResponse,
    )
    monkeypatch.setattr(
        "chatbot.generation.response.final_response.update_qa_ticket_status",
        FakeUpdateTicketStatus,
    )
    monkeypatch.setattr(
        "chatbot.generation.response.final_response.write_insight",
        FakeWriteInsight,
    )
    monkeypatch.setattr(
        "chatbot.generation.response.final_response.dispatch_urgent_alert",
        lambda state: {"status": "skipped"},
    )
    return payloads


def test_final_response_uses_category_fallbacks(monkeypatch) -> None:
    payloads = _patch_final_response_writes(monkeypatch)

    cases = [
        ("결제", PAYMENT_FALLBACK_RESPONSE),
        ("인게임/버그", BUG_FALLBACK_RESPONSE),
        ("FAQ", FAQ_FALLBACK_RESPONSE),
        ("VOC", VOC_FIXED_RESPONSE),
    ]

    for category, expected in cases:
        result = final_response_node(_final_state(category))
        assert result["final_text"] == expected

    assert [payload["final_text"] for payload in payloads] == [expected for _, expected in cases]


def test_final_response_uses_fixed_block_and_review_responses(monkeypatch) -> None:
    _patch_final_response_writes(monkeypatch)

    assert final_response_node(_final_state("FAQ", "BLOCK_RESPONSE"))["final_text"] == BLOCK_RESPONSE
    assert final_response_node(_final_state("FAQ", "REVIEW_QUEUE"))["final_text"] == REVIEW_QUEUE_RESPONSE


def test_dispatch_urgent_alert_creates_github_issue_for_bug_agent(monkeypatch) -> None:
    github_calls = []
    notification_logs = []

    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda message: {"status": "ok"})
    monkeypatch.setattr(
        dispatcher,
        "create_github_issue",
        lambda title, body: github_calls.append((title, body))
        or {"status": "ok", "issue_url": "https://github.com/acme/game/issues/1"},
    )
    monkeypatch.setattr(
        dispatcher,
        "save_notification_log",
        lambda payload: notification_logs.append(payload) or {"status": "ok", "stored": True},
    )
    monkeypatch.setattr(dispatcher, "log_event", lambda *args, **kwargs: {})

    result = dispatcher.dispatch_urgent_alert(
        {
            "ticket_id": 1,
            "session_id": 2,
            "user_id": 3,
            "account_id": 4,
            "category": "in-game-bug",
            "routing_target": "urgent_alert",
            "reasoning_node": "bug_agent",
            "enriched_query": "game closes after loading",
            "final_text": "operator will review",
        }
    )

    assert result["status"] == "skipped"
    assert result["github_issue_result"]["status"] == "ok"
    assert github_calls
    assert github_calls[0][0] == "[인게임 버그] game closes after loading"
    assert [payload["channel"] for payload in notification_logs] == ["github_issue"]


def test_dispatch_urgent_alert_skips_github_issue_for_non_bug(monkeypatch) -> None:
    github_calls = []

    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda message: {"status": "ok"})
    monkeypatch.setattr(
        dispatcher,
        "create_github_issue",
        lambda title, body: github_calls.append((title, body)) or {"status": "ok"},
    )
    monkeypatch.setattr(dispatcher, "save_notification_log", lambda payload: {"status": "ok", "stored": True})
    monkeypatch.setattr(dispatcher, "log_event", lambda *args, **kwargs: {})

    result = dispatcher.dispatch_urgent_alert(
        {
            "ticket_id": 1,
            "category": "payment",
            "routing_target": "urgent_alert",
            "reasoning_node": "payment_agent",
            "enriched_query": "paid item was not delivered",
        }
    )

    assert result["github_issue_result"]["status"] == "skipped"
    assert not github_calls


def test_dispatch_urgent_alert_sends_slack_only_for_review_queue_once(monkeypatch) -> None:
    slack_calls = []
    notification_logs = []

    monkeypatch.setattr(dispatcher, "send_slack_alert", lambda message: slack_calls.append(message) or {"status": "ok"})
    monkeypatch.setattr(dispatcher, "create_github_issue", lambda title, body: {"status": "skipped"})
    monkeypatch.setattr(dispatcher, "notification_log_exists", lambda ticket_id, channel: {"exists": False})
    monkeypatch.setattr(
        dispatcher,
        "save_notification_log",
        lambda payload: notification_logs.append(payload) or {"status": "ok", "stored": True},
    )
    monkeypatch.setattr(dispatcher, "log_event", lambda *args, **kwargs: {})

    result = dispatcher.dispatch_urgent_alert(
        {
            "ticket_id": 1,
            "category": "FAQ",
            "routing_target": "urgent_alert",
            "reasoning_node": "faq_agent",
            "safety_action": "REVIEW_QUEUE",
            "enriched_query": "needs human review",
        }
    )

    assert result["status"] == "ok"
    assert len(slack_calls) == 1
    assert [payload["channel"] for payload in notification_logs] == ["slack"]

    monkeypatch.setattr(dispatcher, "notification_log_exists", lambda ticket_id, channel: {"exists": True})
    result = dispatcher.dispatch_urgent_alert(
        {
            "ticket_id": 1,
            "category": "FAQ",
            "routing_target": "urgent_alert",
            "reasoning_node": "faq_agent",
            "safety_action": "REVIEW_QUEUE",
            "enriched_query": "needs human review again",
        }
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "slack alert already sent for ticket_id"
    assert len(slack_calls) == 1


def test_voc_agent_uses_fallback_for_non_actionable_non_rag_intent(monkeypatch) -> None:
    monkeypatch.setattr(
        voc_agent,
        "_classify_voc",
        lambda text: (_ for _ in ()).throw(AssertionError("Non-actionable VOC should not need another LLM call")),
    )

    result = voc_agent.voc_agent_node(
        {
            "ticket_id": 1,
            "user_id": 1,
            "account_id": 101,
            "enriched_query": "게임 이용 불만",
            "routing_target": "rag_reply",
            "retry_count": 0,
            "is_actionable": False,
            "should_use_rag": False,
            "fallback_reason": "low_information_complaint",
        }
    )

    assert result["draft_text"] == VOC_FIXED_RESPONSE
    assert result["safety_action"] == "AUTO_RESPONSE"
    assert result["safety_reason"] == "low_information_complaint"
    assert result["voc_type"] == "other"
    assert result["sentiment"] == "negative"
    assert result["topic_keywords"] == []

def test_route_by_user_selected_categories() -> None:
    assert route_by_category({"category": "payment"}) == "payment_agent"
    assert route_by_category({"category": "bug"}) == "bug_agent"
    assert route_by_category({"category": "faq"}) == "faq_agent"
    assert route_by_category({"category": "voc"}) == "voc_agent"


def test_route_by_legacy_display_categories() -> None:
    assert route_by_category({"category": "결제"}) == "payment_agent"
    assert route_by_category({"category": "인게임/버그"}) == "bug_agent"
    assert route_by_category({"category": "FAQ"}) == "faq_agent"
    assert route_by_category({"category": "VOC"}) == "voc_agent"

