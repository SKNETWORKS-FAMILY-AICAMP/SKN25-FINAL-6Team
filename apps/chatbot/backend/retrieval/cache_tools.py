from __future__ import annotations

import json

from langchain_core.tools import tool

from chatbot.retrieval.cache_store import get_cached_answer, set_cached_answer


@tool(parse_docstring=True)
def get_cache(query_hash: str) -> str:
    """Retrieve a cached answer for the given query hash.

    Args:
        query_hash: SHA-256 hex digest of the normalized query.
    """
    return json.dumps(get_cached_answer(query_hash), ensure_ascii=False)


@tool(parse_docstring=True)
def set_cache(query_hash: str, answer: str, ttl: int = 3600) -> str:
    """Store an answer in the cache under the given query hash.

    Args:
        query_hash: SHA-256 hex digest of the normalized query.
        answer: Answer text to cache.
        ttl: Cache lifetime in seconds.
    """
    return json.dumps(set_cached_answer(query_hash, answer, ttl), ensure_ascii=False)
