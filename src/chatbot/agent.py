from __future__ import annotations

from typing import Any

from chatbot.prompts.system_prompt import CHATBOT_SYSTEM_PROMPT
from chatbot.schemas import ChatbotState
from chatbot.tools.registry import CHATBOT_TOOLS
from config import settings


def build_chatbot_agent() -> Any:
    """Build the create_agent baseline so it can also be mounted in graph nodes."""
    from langchain.agents import create_agent

    return create_agent(
        model=settings.openai_model,
        tools=CHATBOT_TOOLS,
        system_prompt=CHATBOT_SYSTEM_PROMPT,
        state_schema=ChatbotState,
    )


_agent_instance: Any | None = None


def get_chatbot_agent() -> Any:
    """Return the shared chatbot agent, building it only when it is first invoked."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = build_chatbot_agent()
    return _agent_instance


class LazyChatbotAgent:
    """Backward-compatible lazy proxy for code that imports chatbot.agent.agent."""

    def invoke(self, state: ChatbotState | dict[str, Any]) -> dict[str, Any]:
        return get_chatbot_agent().invoke(state)

    def __getattr__(self, name: str) -> Any:
        return getattr(get_chatbot_agent(), name)


def invoke_chatbot_agent(
    state: ChatbotState | dict[str, Any],
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    """Invoke the chatbot agent through a stable graph-ready interface."""
    runtime_agent = agent_instance or get_chatbot_agent()
    return runtime_agent.invoke(state)


agent = LazyChatbotAgent()
