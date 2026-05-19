from __future__ import annotations

from chatbot.agent import invoke_bug_agent
from chatbot.agents.drafting_agent import build_draft_update
from chatbot.agents.policies import BUG_POLICY
from chatbot.schemas import ChatbotState


def bug_agent_node(state: ChatbotState) -> dict:
    result = invoke_bug_agent(state)
    return build_draft_update(state, result, BUG_POLICY.name)
