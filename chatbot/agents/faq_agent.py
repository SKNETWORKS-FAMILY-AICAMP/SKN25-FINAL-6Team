from __future__ import annotations

from chatbot.agents.reasoning import reasoning_agent_node
from chatbot.schemas import ChatbotState


def faq_agent_node(state: ChatbotState) -> dict:
    return reasoning_agent_node(state, "faq_agent")
