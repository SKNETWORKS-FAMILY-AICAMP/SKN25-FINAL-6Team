from __future__ import annotations

import time
from typing import TypedDict


class CacheLookupResult(TypedDict, total=False):
    hit: bool
    answer: str


_CACHE: dict[str, tuple[str, float]] = {}


def get_cached_answer(query_hash: str) -> CacheLookupResult:
    entry = _CACHE.get(query_hash)
    if entry is None:
        return {"hit": False}

    answer, expires_at = entry
    if time.time() > expires_at:
        _CACHE.pop(query_hash, None)
        return {"hit": False}

    return {"hit": True, "answer": answer}


def set_cached_answer(query_hash: str, answer: str, ttl: int = 3600) -> dict[str, object]:
    _CACHE[query_hash] = (answer, time.time() + ttl)
    return {"status": "ok", "query_hash": query_hash, "ttl": ttl}


def clear_cache_for_tests() -> None:
    _CACHE.clear()
