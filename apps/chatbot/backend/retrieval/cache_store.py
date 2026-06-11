from __future__ import annotations

import os
import time
import json
from functools import lru_cache
from typing import TypedDict


class RetrievalCacheLookupResult(TypedDict, total=False):
    """Return shape for cached FAQ/RAG retrieval documents."""

    hit: bool
    documents: list[dict]


_RETRIEVAL_CACHE: dict[str, tuple[list[dict], float]] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    """Read boolean-like environment variables such as REDIS_ENABLED."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cache_key(query_hash: str, *, namespace: str = "answer") -> str:
    """Build a versioned Redis key without exposing the original user query."""
    prefix = os.environ.get("CACHE_KEY_PREFIX", "chatbot").strip() or "chatbot"
    return f"{prefix}:faq:{namespace}:v1:{query_hash}"


@lru_cache(maxsize=1)
def _redis_client():
    """Create a Redis client when enabled, returning None on any setup failure."""
    if not _env_flag("REDIS_ENABLED"):
        return None

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        from redis import Redis

        client = Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _get_memory_retrieval_cache(query_hash: str) -> RetrievalCacheLookupResult:
    """Read cached retrieved documents from local memory and enforce TTL expiry."""
    entry = _RETRIEVAL_CACHE.get(query_hash)
    if entry is None:
        return {"hit": False}

    documents, expires_at = entry
    if time.time() > expires_at:
        _RETRIEVAL_CACHE.pop(query_hash, None)
        return {"hit": False}

    return {"hit": True, "documents": documents}


def _set_memory_retrieval_cache(query_hash: str, documents: list[dict], ttl: int) -> None:
    """Store retrieved documents in the local fallback cache with TTL."""
    _RETRIEVAL_CACHE[query_hash] = (documents, time.time() + ttl)


def get_cached_retrieval(query_hash: str) -> RetrievalCacheLookupResult:
    """Return cached retrieved documents from Redis first, then memory fallback.

    This stores document evidence, not final answers, so downstream evidence and
    safety checks can still run with the documents used for generation.
    """
    client = _redis_client()
    if client is not None:
        try:
            cached_json = client.get(_cache_key(query_hash, namespace="retrieval"))
            if cached_json is not None:
                return {"hit": True, "documents": json.loads(cached_json)}
        except Exception:
            pass

    return _get_memory_retrieval_cache(query_hash)


def set_cached_retrieval(query_hash: str, documents: list[dict], ttl: int = 3600) -> dict[str, object]:
    """Persist retrieved FAQ/RAG documents using Redis when available.

    If Redis is disabled or unavailable, the documents are stored in the
    in-memory fallback cache. Final answer text is intentionally not cached here.
    """
    client = _redis_client()
    backend = "memory"
    if client is not None:
        try:
            client.setex(
                _cache_key(query_hash, namespace="retrieval"),
                ttl,
                json.dumps(documents, ensure_ascii=False, default=str),
            )
            backend = "redis"
        except Exception:
            _set_memory_retrieval_cache(query_hash, documents, ttl)
    else:
        _set_memory_retrieval_cache(query_hash, documents, ttl)

    return {
        "status": "ok",
        "query_hash": query_hash,
        "ttl": ttl,
        "backend": backend,
        "document_count": len(documents),
    }


def clear_cache_for_tests() -> None:
    """Reset local cache state and Redis client memoization between tests."""
    _RETRIEVAL_CACHE.clear()
    cache_clear = getattr(_redis_client, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def clear_faq_cache(namespace: str | None = None) -> dict[str, object]:
    """Clear FAQ answer/retrieval cache from memory and Redis when available."""
    if namespace in (None, "retrieval"):
        _RETRIEVAL_CACHE.clear()

    deleted = 0
    backend = "memory"
    client = _redis_client()
    if client is not None:
        backend = "redis"
        namespaces = [namespace] if namespace else ["answer", "retrieval"]
        for cache_namespace in namespaces:
            pattern = _cache_key("*", namespace=str(cache_namespace))
            try:
                for key in client.scan_iter(match=pattern):
                    deleted += int(client.delete(key) or 0)
            except Exception:
                backend = "redis_error"

    return {
        "status": "ok",
        "backend": backend,
        "namespace": namespace or "all",
        "redis_deleted": deleted,
        "memory_answer_entries": 0,
        "memory_retrieval_entries": len(_RETRIEVAL_CACHE),
    }
