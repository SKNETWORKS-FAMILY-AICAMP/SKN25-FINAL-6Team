from __future__ import annotations

import json
import time

from langchain_core.tools import tool

_CACHE: dict[str, tuple[str, float]] = {}


@tool(parse_docstring=True)
def get_cache(query_hash: str) -> str:
    """Retrieve a cached answer for the given query hash.

    Args:
        query_hash: SHA-256 hex digest of the normalized query.
    """
    entry = _CACHE.get(query_hash)
    if entry is None:
        return json.dumps({"hit": False})
    answer, expires_at = entry
    if time.time() > expires_at:
        del _CACHE[query_hash]
        return json.dumps({"hit": False})
    return json.dumps({"hit": True, "answer": answer})


@tool(parse_docstring=True)
def set_cache(query_hash: str, answer: str, ttl: int = 3600) -> str:
    """Store an answer in the cache under the given query hash.

    Args:
        query_hash: SHA-256 hex digest of the normalized query.
        answer: Answer text to cache.
        ttl: Cache lifetime in seconds.
    """
    _CACHE[query_hash] = (answer, time.time() + ttl)
    return json.dumps({"status": "ok", "query_hash": query_hash, "ttl": ttl})
