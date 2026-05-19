from __future__ import annotations

from chatbot.agent import invoke_payment_agent
from chatbot.agents.drafting_agent import build_draft_update
from chatbot.agents.policies import PAYMENT_POLICY
from chatbot.schemas import ChatbotState


def payment_agent_node(state: ChatbotState) -> dict:
    result = invoke_payment_agent(state)
    return build_draft_update(state, result, PAYMENT_POLICY.name)
