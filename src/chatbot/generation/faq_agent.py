from __future__ import annotations

from chatbot.agent import invoke_faq_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import FAQ_POLICY
from chatbot.schemas import ChatbotState


def faq_agent_node(state: ChatbotState) -> dict:
    result = invoke_faq_agent(state)
    return build_draft_update(state, result, FAQ_POLICY.name)
