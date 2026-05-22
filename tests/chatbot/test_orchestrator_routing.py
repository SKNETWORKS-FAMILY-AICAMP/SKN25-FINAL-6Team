from __future__ import annotations

from chatbot.chains.routing import route_by_category
from chatbot.generation.orchestrator import _classify, _rule_based_route


def test_galaxy_payment_how_to_routes_to_faq_without_account() -> None:
    assert _rule_based_route("갤럭시 스토어 결제 방법 알려주세요", account_id=None) == (
        "FAQ",
        "rag_reply",
        "payment_policy_or_how_to",
    )


def test_galaxy_missing_paid_item_routes_to_payment() -> None:
    assert _rule_based_route("갤럭시 스토어에서 결제했는데 상품이 안 들어왔어요", account_id=None) == (
        "결제",
        "urgent_alert",
        "payment_action_or_account_specific",
    )


def test_payment_question_with_account_routes_to_payment() -> None:
    assert _rule_based_route("갤럭시 스토어 결제 방법 알려주세요", account_id=10) == (
        "결제",
        "urgent_alert",
        "payment_action_or_account_specific",
    )


def test_classify_uses_rule_before_llm(monkeypatch) -> None:
    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM classifier should not run for high-signal payment routes")

    monkeypatch.setattr("chatbot.generation.orchestrator._classify_with_llm", fail_llm)

    assert _classify(1, "갤럭시 스토어 결제 방법 알려주세요", account_id=None) == (
        "FAQ",
        "rag_reply",
        "rule",
        "payment_policy_or_how_to",
    )


def test_route_by_normalized_categories() -> None:
    assert route_by_category({"category": "결제"}) == "payment_agent"
    assert route_by_category({"category": "인게임/버그"}) == "bug_agent"
    assert route_by_category({"category": "FAQ"}) == "faq_agent"
