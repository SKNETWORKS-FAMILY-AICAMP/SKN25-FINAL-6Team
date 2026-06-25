from __future__ import annotations

import os
from typing import Any

from collections.abc import Sequence

from generation.policies import BUG_POLICY, PAYMENT_POLICY
from observability.langfuse import link_chatbot_trace
from schemas import ChatbotState
from common.observability.langfuse import get_langchain_config, observe_if_enabled
from common.observability.logger import record_chat_model_usage


def build_chatbot_agent(
    *,
    system_prompt: str,
    tools: Sequence[Any],
) -> Any:
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        raise RuntimeError("LLM_API_KEY is required.")

    chat_model = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
    )

    return create_agent(
        model=chat_model,
        tools=list(tools),
        system_prompt=system_prompt,
        state_schema=ChatbotState,
    )


def _build_and_invoke_agent(
    state: ChatbotState | dict[str, Any],
    *,
    system_prompt: str,
    tools: Sequence[Any],
    usage_component: str,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    runtime_agent = agent_instance or build_chatbot_agent(
        system_prompt=system_prompt,
        tools=tools,
    )
    result = runtime_agent.invoke(state, config=get_langchain_config())
    for message in result.get("messages") or []:
        record_chat_model_usage(usage_component, os.environ.get("LLM_MODEL"), message)
    return result


@observe_if_enabled(
    name="payment_reasoning_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "payment"],
)
def invoke_payment_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "payment"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "routing_target": state.get("routing_target"),
            "payment_intent_type": state.get("payment_intent_type"),
            "retrieved_count": len(state.get("retrieved_documents") or []),
        },
    )
    result = _build_and_invoke_agent(
        state,
        system_prompt=PAYMENT_POLICY.system_prompt,
        tools=PAYMENT_POLICY.tools,
        usage_component="payment_agent",
        agent_instance=agent_instance,
    )
    link_chatbot_trace(
        state,
        tags=["feature:generation", "payment"],
        metadata_source={**state, **result},
        output_payload={"message_count": len(result.get("messages") or [])},
    )
    return result


@observe_if_enabled(
    name="bug_reasoning_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "bug"],
)
def invoke_bug_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "routing_target": state.get("routing_target"),
            "bug_report_form_present": bool(state.get("bug_report_form")),
            "retrieved_count": len(state.get("retrieved_documents") or []),
        },
    )
    result = _build_and_invoke_agent(
        state,
        system_prompt=BUG_POLICY.system_prompt,
        tools=BUG_POLICY.tools,
        usage_component="bug_agent",
        agent_instance=agent_instance,
    )
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        metadata_source={**state, **result},
        output_payload={"message_count": len(result.get("messages") or [])},
    )
    return result
