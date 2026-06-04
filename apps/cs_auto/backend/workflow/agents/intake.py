"""LangChain intake agent for operation workflow planning."""

from __future__ import annotations

import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..prompts import INTAKE_SYSTEM_PROMPT, INTAKE_USER_PROMPT, IntakeAgentResponse, render_state
from ..state import OperationState


# run_intake_agent ?? ??
def run_intake_agent(state: OperationState) -> IntakeAgentResponse:
    """Classify the ticket and produce the initial workflow plan."""

    llm = ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    ).with_structured_output(IntakeAgentResponse)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", INTAKE_SYSTEM_PROMPT),
            ("human", INTAKE_USER_PROMPT),
        ]
    )
    messages = prompt.invoke({"state_json": render_state(state)}).to_messages()
    return IntakeAgentResponse.model_validate(llm.invoke(messages))
