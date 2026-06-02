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


def normalize_query_text(text: str | None) -> str:
    return " ".join(str(text or "").strip().split())


def _canonical_category(category: Any) -> str:
    value = str(category or "").strip()
    return CATEGORY_ALIASES.get(value, CATEGORY_ALIASES.get(value.lower(), value.lower()))


class QueryRewriteResult(BaseModel):
    query_text: str = Field(description="Short Korean retrieval query")


def rewrite_query_with_llm(
    *,
    original_query: str,
    failed_query: str,
    category: Any,
    failure_reason: str,
) -> dict[str, Any]:
    """Rewrite a failed retrieval query once, using only already-masked text."""
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
