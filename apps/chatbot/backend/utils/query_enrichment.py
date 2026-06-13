from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field


CATEGORY_ALIASES = {
    "payment": "payment",
    "결제": "payment",
    "bug": "bug",
    "인게임/버그": "bug",
    "faq": "faq",
    "FAQ": "faq",
    "voc": "voc",
    "VOC": "voc",
}


# 검색/분류 전에 공백을 정리해 같은 의미의 입력이 같은 normalized_query에 가깝게 들어가도록 한다.
def normalize_query_text(text: str | None) -> str:
    return " ".join(str(text or "").strip().split())


# category 표시값이 한글/영문/대소문자로 섞여 들어와도 내부 category 이름으로 맞춘다.
def _canonical_category(category: Any) -> str:
    value = str(category or "").strip()
    return CATEGORY_ALIASES.get(value, CATEGORY_ALIASES.get(value.lower(), value.lower()))


# LLM rewrite는 답변 생성이 아니라 검색어만 짧게 다시 만드는 데 사용한다.
class QueryRewriteResult(BaseModel):
    query_text: str = Field(description="Short Korean retrieval query")


# FAQ 검색이 실패했을 때 한 번만 LLM으로 검색어를 재작성한다.
# 원문은 이미 input_preprocessing에서 마스킹된 값을 사용해야 한다.
def rewrite_query_with_llm(
    *,
    original_query: str,
    failed_query: str,
    category: Any,
    failure_reason: str,
) -> dict[str, Any]:
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("QUERY_REWRITE_MODEL") or os.environ.get("QUERY_ENRICHMENT_MODEL") or os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return {
            "query_text": "",
            "method": "skipped",
            "reason": "missing_llm_settings",
        }

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0,
            timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        ).with_structured_output(QueryRewriteResult)
        result = llm.invoke(
            [
                (
                    "system",
                    "You rewrite Korean game customer-support RAG queries. "
                    "The input is already privacy-masked. "
                    "Return a concise search query, not an answer. "
                    "Preserve the user's core issue and convert slang or vague wording into FAQ/search terms. "
                    "Avoid adding unsupported facts, dates, payment status, or account-specific claims.",
                ),
                (
                    "user",
                    "\n".join(
                        [
                            f"category: {_canonical_category(category)}",
                            f"original_query: {original_query}",
                            f"failed_query: {failed_query}",
                            f"failure_reason: {failure_reason}",
                        ]
                    ),
                ),
            ]
        )
        rewritten = normalize_query_text(result.query_text)
        if not rewritten or rewritten == normalize_query_text(failed_query):
            return {
                "query_text": "",
                "method": "llm_rewrite",
                "reason": "empty_or_same_query",
                "model": model,
            }
        return {
            "query_text": rewritten,
            "method": "llm_rewrite",
            "reason": None,
            "model": model,
        }
    except Exception as exc:
        return {
            "query_text": "",
            "method": "llm_rewrite",
            "reason": type(exc).__name__,
            "model": model,
        }
