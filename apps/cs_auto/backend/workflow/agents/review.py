"""LangChain review agent for operation workflow safety checks."""

from __future__ import annotations

import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..prompts import REVIEW_SYSTEM_PROMPT, REVIEW_USER_PROMPT, ReviewAgentResponse, render_state
from ..state import OperationState


def run_review_agent(state: OperationState) -> ReviewAgentResponse:
    """Review the drafted response and decide the approval route."""

    llm = ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    ).with_structured_output(ReviewAgentResponse)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REVIEW_SYSTEM_PROMPT),
            ("human", REVIEW_USER_PROMPT),
        ]
    )
    messages = prompt.invoke({"state_json": render_state(state)}).to_messages()
    return ReviewAgentResponse.model_validate(llm.invoke(messages))
