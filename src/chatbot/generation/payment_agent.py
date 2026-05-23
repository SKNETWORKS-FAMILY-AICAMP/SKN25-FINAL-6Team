from __future__ import annotations

from chatbot.agent import invoke_payment_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import PAYMENT_POLICY
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.schemas import ChatbotState


def payment_agent_node(state: ChatbotState) -> dict:
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    result = invoke_payment_agent(state)
    update = build_draft_update(state, result, PAYMENT_POLICY.name)
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_length": len(update.get("draft_text") or "")},
    )
    return update
