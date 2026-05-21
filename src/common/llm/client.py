"""LangChain-based structured LLM client."""

from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


load_dotenv()

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def invoke_structured_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredModel],
) -> StructuredModel:
    """Invoke ChatOpenAI and return a Pydantic-validated structured response."""

    llm = ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    )
    structured_llm = llm.with_structured_output(response_model)
    response = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return response_model.model_validate(response)
