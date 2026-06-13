from __future__ import annotations

import os
from typing import Any

from collections.abc import Sequence

from chatbot.generation.policies import BUG_POLICY, PAYMENT_POLICY
from chatbot.schemas import ChatbotState


# 결제/버그 agent를 LangChain create_agent 형태로 실행하기 위한 공통 builder다.
# FAQ/RAG는 검색-근거-답변 흐름이 별도 구현되어 있어 이 helper를 타지 않는다.
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


# agent 인스턴스가 주어지면 그대로 쓰고, 없으면 policy prompt/tool로 새 agent를 만든 뒤 state를 invoke한다.
def _build_and_invoke_agent(
    state: ChatbotState | dict[str, Any],
    *,
    system_prompt: str,
    tools: Sequence[Any],
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    runtime_agent = agent_instance or build_chatbot_agent(
        system_prompt=system_prompt,
        tools=tools,
    )
    return runtime_agent.invoke(state)


# payment_agent 노드에서 결제 전용 prompt/tool 조합으로 agent를 호출할 때 사용하는 adapter다.
def invoke_payment_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    return _build_and_invoke_agent(
        state,
        system_prompt=PAYMENT_POLICY.system_prompt,
        tools=PAYMENT_POLICY.tools,
        agent_instance=agent_instance,
    )


# bug_agent 노드에서 버그 전용 prompt/tool 조합으로 agent를 호출할 때 사용하는 adapter다.
def invoke_bug_agent(
    state: ChatbotState | dict[str, Any],
    *,
    agent_instance: Any | None = None,
) -> dict[str, Any]:
    return _build_and_invoke_agent(
        state,
        system_prompt=BUG_POLICY.system_prompt,
        tools=BUG_POLICY.tools,
        agent_instance=agent_instance,
    )
