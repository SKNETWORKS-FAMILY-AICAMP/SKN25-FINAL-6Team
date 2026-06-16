"""LangChain-based structured LLM client."""

from __future__ import annotations

import os
from typing import Any, TypeVar

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel


load_dotenv()

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _disable_tracing_without_langsmith_key() -> None:
    """Prevent tracing auth noise when LangSmith is not configured."""

    if os.environ.get("LANGSMITH_API_KEY", "").strip() or os.environ.get("LANGCHAIN_API_KEY", "").strip():
        return
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


_disable_tracing_without_langsmith_key()


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _resolve_chat_api_key(*, base_url: str | None) -> str:
    api_key = _first_env("CS_AUTO_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
    if api_key:
        return api_key
    if base_url:
        return "vllm"
    raise KeyError("LLM_API_KEY")


def build_chat_openai_kwargs(*, model: str | None = None) -> dict[str, Any]:
    """Build shared ChatOpenAI kwargs, including optional OpenAI-compatible base_url."""

    base_url = _first_env("CS_AUTO_LLM_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL")
    kwargs: dict[str, Any] = {
        "model": model or os.environ["LLM_MODEL"],
        "api_key": _resolve_chat_api_key(base_url=base_url),
        "temperature": 0,
        "timeout": float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
    }
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return kwargs


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


def get_chat_llm(*, model: str | None = None) -> ChatOpenAI:
    """Build the shared ChatOpenAI client with common timeout and tracing config."""

    return ChatOpenAI(**build_chat_openai_kwargs(model=model))


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
    llm = get_chat_llm()
    structured_llm = llm.with_structured_output(response_model)
    response = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return response_model.model_validate(response)
