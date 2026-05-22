from __future__ import annotations

from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from chatbot.safety import safety_layer


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
            "draft_text": "갤럭시 스토어 결제는 스토어 앱에서 결제 수단을 선택해 진행할 수 있습니다.",
            "retrieved_documents": [{"chunk_text": "갤럭시 스토어 결제 방법 안내 문서"}],
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
        draft_text="결제 내역을 확인한 뒤 안내드리겠습니다.",
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
            "draft_text": "문의 결과는 test@example.com 으로 안내됩니다.",
            "retrieved_documents": [{"chunk_text": "문의 결과는 이메일로 안내됩니다."}],
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
            "draft_text": "문의 결과는 test@example.com 으로 안내됩니다.",
            "retrieved_documents": [{"chunk_text": "문의 결과는 이메일로 안내됩니다."}],
            "retry_count": 2,
            "category": "FAQ",
            "routing_target": "rag_reply",
        }
    )

    assert update["safety_action"] == "SAFE_FALLBACK"
    assert update["draft_text"] == SAFE_FALLBACK_RESPONSE
    assert update["retry_count"] == 3
    assert payloads[0]["safety_action"] == "SAFE_FALLBACK"
