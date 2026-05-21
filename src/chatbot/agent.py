from __future__ import annotations

import os
from typing import Any

from collections.abc import Sequence

from chatbot.generation.policies import BUG_POLICY, FAQ_POLICY, PAYMENT_POLICY
from chatbot.schemas import ChatbotState


def build_chatbot_agent(
    *,
    system_prompt: str,
    tools: Sequence[Any],
) -> Any:
    """Build a create_agent instance for one StateGraph category node policy."""
    from langchain.agents import create_agent

    return create_agent(
        model=os.environ["LLM_MODEL"],
        tools=list(tools),
        system_prompt=system_prompt,
        state_schema=ChatbotState,
    )


def _build_and_invoke_agent(
    state: ChatbotState | dict[str, Any],
    *,
    system_prompt: str,
    tools: Sequence[Any],
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    """Build a create_agent instance when needed, then invoke it with state."""
    runtime_agent = agent_instance or build_chatbot_agent(
        system_prompt=system_prompt,
        tools=tools,
    )
    return runtime_agent.invoke(state)


def invoke_payment_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    """Invoke the payment-specific create_agent instance."""
    return _build_and_invoke_agent(
        state,
        system_prompt=PAYMENT_POLICY.system_prompt,
        tools=PAYMENT_POLICY.tools,
        agent_instance=agent_instance,
    )


def invoke_faq_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    """Invoke the FAQ/RAG-specific create_agent instance."""
    return _build_and_invoke_agent(
        state,
        system_prompt=FAQ_POLICY.system_prompt,
        tools=FAQ_POLICY.tools,
        agent_instance=agent_instance,
    )


def invoke_bug_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    """Invoke the bug-specific create_agent instance."""
    return _build_and_invoke_agent(
        state,
        system_prompt=BUG_POLICY.system_prompt,
        tools=BUG_POLICY.tools,
        agent_instance=agent_instance,
    )
