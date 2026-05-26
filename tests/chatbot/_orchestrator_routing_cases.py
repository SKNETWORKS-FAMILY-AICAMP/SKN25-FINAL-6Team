from __future__ import annotations

from chatbot.chains.routing import route_by_category
from chatbot.generation.orchestrator import _classify, _route_from_intent
from chatbot.schemas import RoutingIntent


def test_llm_intent_normalizes_slang_payment_how_to_to_faq(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatbot.generation.orchestrator._normalize_intent_with_llm",
        lambda query: RoutingIntent(
            intent="payment_how_to",
            normalized_query="갤럭시 스토어 결제 방법",
            requires_account_lookup=False,
            should_use_rag=True,
            reason="slang payment how-to",
        ),
    )

    assert _classify(1, "galaxy store 결제 어캐함?", account_id=None) == (
        "FAQ",
        "rag_reply",
        "llm_intent",
        "intent:payment_how_to; slang payment how-to",
        "갤럭시 스토어 결제 방법",
        True,
        True,
        None,
    )


def test_llm_intent_routes_missing_payment_to_operation(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatbot.generation.orchestrator._normalize_intent_with_llm",
        lambda query: RoutingIntent(
            intent="payment_missing_item",
            normalized_query="결제 상품 미지급",
            requires_account_lookup=True,
            should_use_rag=False,
            reason="paid item is missing",
        ),
    )

    assert _classify(1, "결제했는데 상품 안 들어옴", account_id=None) == (
        "결제",
        "urgent_alert",
        "llm_intent",
        "intent:payment_missing_item; paid item is missing",
        "결제 상품 미지급",
        True,
        False,
        None,
    )


def test_llm_intent_keeps_payment_how_to_in_faq_even_with_account(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatbot.generation.orchestrator._normalize_intent_with_llm",
        lambda query: RoutingIntent(
            intent="payment_how_to",
            normalized_query="갤럭시 스토어 결제 방법",
            requires_account_lookup=False,
            should_use_rag=True,
            reason="payment how-to but account is present",
        ),
    )

    assert _classify(1, "갤럭시 스토어 결제 방법 알려주세요", account_id=10) == (
        "FAQ",
        "rag_reply",
        "llm_intent",
        "intent:payment_how_to; payment how-to but account is present",
        "갤럭시 스토어 결제 방법",
        True,
        True,
        None,
    )


def test_route_from_intent_sends_bug_how_to_to_faq() -> None:
    assert _route_from_intent(
        RoutingIntent(
            intent="bug_how_to",
            normalized_query="게임 실행 오류 해결 방법",
            requires_account_lookup=False,
            should_use_rag=True,
            reason="general troubleshooting",
        )
    ) == ("FAQ", "rag_reply", "intent:bug_how_to; general troubleshooting")


def test_route_from_intent_prioritizes_general_rag_over_account_lookup() -> None:
    assert _route_from_intent(
        RoutingIntent(
            intent="payment_how_to",
            normalized_query="갤럭시 스토어 결제 방법",
            is_actionable=True,
            requires_account_lookup=True,
            should_use_rag=True,
            reason="general payment guide despite logged-in account",
        ),
        account_id=101,
    ) == ("FAQ", "rag_reply", "intent:payment_how_to; general payment guide despite logged-in account")


def test_llm_intent_routes_non_actionable_complaint_to_voc_without_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatbot.generation.orchestrator._normalize_intent_with_llm",
        lambda query: RoutingIntent(
            intent="voc",
            normalized_query="게임 이용 불만",
            is_actionable=False,
            requires_account_lookup=False,
            should_use_rag=False,
            fallback_reason="low_information_complaint",
            reason="vague emotional complaint without a concrete issue",
        ),
    )

    assert _classify(1, "게임 왜 이따위임?", account_id=None) == (
        "VOC",
        "rag_reply",
        "llm_intent",
        "intent:voc; vague emotional complaint without a concrete issue",
        "게임 이용 불만",
        False,
        False,
        "low_information_complaint",
    )


def test_classify_falls_back_to_structured_classifier_when_intent_fails(monkeypatch) -> None:
    monkeypatch.setattr("chatbot.generation.orchestrator._normalize_intent_with_llm", lambda query: (_ for _ in ()).throw(RuntimeError("intent failed")))
    monkeypatch.setattr(
        "chatbot.generation.orchestrator._classify_with_llm",
        lambda ticket_id, query: type(
            "ClassifierResult",
            (),
            {
                "category": "FAQ",
                "routing_target": "rag_reply",
                "reason": "classifier fallback",
            },
        )(),
    )

    assert _classify(1, "갤럭시 스토어 결제 방법 알려주세요", account_id=None) == (
        "FAQ",
        "rag_reply",
        "llm",
        "classifier fallback",
        "갤럭시 스토어 결제 방법 알려주세요",
        None,
        None,
        None,
    )


def test_classify_defaults_to_faq_when_all_llm_routing_fails(monkeypatch) -> None:
    monkeypatch.setattr("chatbot.generation.orchestrator._normalize_intent_with_llm", lambda query: (_ for _ in ()).throw(RuntimeError("intent failed")))
    monkeypatch.setattr("chatbot.generation.orchestrator._classify_with_llm", lambda ticket_id, query: (_ for _ in ()).throw(RuntimeError("classifier failed")))

    assert _classify(1, "갤럭시 스토어 결제 방법 알려주세요", account_id=None) == (
        "FAQ",
        "rag_reply",
        "fallback",
        "intent_and_classifier_unavailable",
        "갤럭시 스토어 결제 방법 알려주세요",
        None,
        None,
        None,
    )


def test_route_by_normalized_categories() -> None:
    assert route_by_category({"category": "결제"}) == "payment_agent"
    assert route_by_category({"category": "인게임/버그"}) == "bug_agent"
    assert route_by_category({"category": "FAQ"}) == "faq_agent"
