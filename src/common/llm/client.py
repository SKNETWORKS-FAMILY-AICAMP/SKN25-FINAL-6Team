"""LangChain-based structured LLM client."""

from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel


load_dotenv()

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def get_query_embedding(query: str) -> list[float] | None:
    """쿼리 텍스트의 임베딩 벡터를 반환합니다. 실패 시 None을 반환합니다.

    EMBEDDING_MODEL 환경변수가 없으면 text-embedding-3-small을 기본값으로 사용합니다.
    임베딩 생성 실패 시 keyword-only 검색으로 graceful fallback할 수 있도록 None을 반환합니다.
    """
    try:
        model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        embedder = OpenAIEmbeddings(model=model, api_key=os.environ["LLM_API_KEY"])
        return embedder.embed_query(query)
    except Exception:
        return None


def invoke_structured_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredModel],
) -> StructuredModel:
    """ChatOpenAI를 호출하고 Pydantic 검증된 구조화 응답을 반환합니다.

    with_structured_output으로 JSON 모드를 활성화하고,
    model_validate로 타입 안전성을 재확인합니다.
    LLM_TIMEOUT_SECONDS 기본값 60: LLM 단일 호출 최대 허용 시간 —
    워크플로우 전체(다단계)는 frontend에서 120초를 별도로 적용합니다.
    """
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
