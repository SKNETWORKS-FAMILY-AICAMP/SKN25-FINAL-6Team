from __future__ import annotations

from chatbot.chains.routing import route_by_category
from chatbot.generation.ticket_preprocess import ticket_preprocess_node


class FakeWriteQaTicket:
    @staticmethod
    def invoke(payload: dict) -> dict:
        return {"status": "ok", "stored": True, "ticket_id": payload["payload"]["ticket_id"]}


def _base_state(category: str) -> dict:
    return {
        "ticket_id": 1,
        "user_id": 10,
        "account_id": 20,
        "session_id": "route-test-1",
        "source_type": "chatbot",
        "raw_query": "문의합니다",
        "masked_content": "문의합니다",
        "category": category,
    }


def test_preprocess_defaults_payment_category_to_payment_agent(monkeypatch) -> None:
    from chatbot.generation import ticket_preprocess

    monkeypatch.setattr(ticket_preprocess, "write_qa_ticket", FakeWriteQaTicket)

    update = ticket_preprocess_node(_base_state("payment"))

    assert update["routing_target"] == "payment_agent"
    assert route_by_category(update) == "payment_agent"


def test_preprocess_defaults_faq_category_to_faq_agent(monkeypatch) -> None:
    from chatbot.generation import ticket_preprocess

    monkeypatch.setattr(ticket_preprocess, "write_qa_ticket", FakeWriteQaTicket)

    update = ticket_preprocess_node(_base_state("faq"))

    assert update["routing_target"] == "faq_agent"
    assert route_by_category(update) == "faq_agent"


def test_preprocess_preserves_frontend_routing_target(monkeypatch) -> None:
    from chatbot.generation import ticket_preprocess

    monkeypatch.setattr(ticket_preprocess, "write_qa_ticket", FakeWriteQaTicket)
    state = _base_state("payment") | {"routing_target": "faq_agent"}

    update = ticket_preprocess_node(state)

    assert update["routing_target"] == "faq_agent"
    assert route_by_category(update) == "faq_agent"
