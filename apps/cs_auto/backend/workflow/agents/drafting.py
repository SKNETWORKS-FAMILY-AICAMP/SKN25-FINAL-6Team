"""LangChain drafting agent for operation workflow responses."""

from __future__ import annotations

import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..prompts import DRAFTING_SYSTEM_PROMPT, DRAFTING_USER_PROMPT, DraftingAgentResponse, render_state_for_drafting
from ..state import OperationState


def run_drafting_agent(state: OperationState) -> DraftingAgentResponse:
    """Draft the customer or operator-facing message for the current state."""

    llm = ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    ).with_structured_output(DraftingAgentResponse)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", DRAFTING_SYSTEM_PROMPT),
            ("human", DRAFTING_USER_PROMPT),
        ]
    )
    messages = prompt.invoke({"state_json": render_state_for_drafting(state)}).to_messages()
    return DraftingAgentResponse.model_validate(llm.invoke(messages))
