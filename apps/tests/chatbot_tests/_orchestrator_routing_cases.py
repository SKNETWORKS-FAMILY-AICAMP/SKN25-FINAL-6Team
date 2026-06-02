from __future__ import annotations

from chatbot.chains.routing import route_by_category


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
