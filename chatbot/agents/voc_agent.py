from __future__ import annotations

from chatbot.agents.reasoning import reasoning_agent_node
from chatbot.schemas import ChatbotState


def voc_agent_node(state: ChatbotState) -> dict:
    return reasoning_agent_node(state, "voc_agent")
