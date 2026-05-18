from __future__ import annotations

from chatbot.agents.drafting_agent import drafting_agent_node
from chatbot.schemas import ChatbotState


def faq_agent_node(state: ChatbotState) -> dict:
    return drafting_agent_node(state, "faq_agent")
