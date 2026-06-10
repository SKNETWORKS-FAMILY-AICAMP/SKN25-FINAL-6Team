from __future__ import annotations

import os
import time
import json
from functools import lru_cache
from typing import TypedDict


# FAQ/RAG 검색 결과 캐시의 반환 형태다.
# 최종 답변 텍스트가 아니라 검색된 근거 문서만 저장한다.
class RetrievalCacheLookupResult(TypedDict, total=False):
    hit: bool
    documents: list[dict]


_RETRIEVAL_CACHE: dict[str, tuple[list[dict], float]] = {}


# 환경변수에서 boolean 값을 읽는 공통 helper다.
# Redis가 꺼져 있으면 retrieval cache는 프로세스 메모리 fallback을 사용한다.
def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# 원문 query를 Redis key에 직접 노출하지 않기 위해 hash 기반 key를 만든다.
def _cache_key(query_hash: str, *, namespace: str = "answer") -> str:
    prefix = os.environ.get("CACHE_KEY_PREFIX", "chatbot").strip() or "chatbot"
    return f"{prefix}:faq:{namespace}:v1:{query_hash}"


@lru_cache(maxsize=1)
def _redis_client():
    # Redis가 활성화되어 있고 연결이 가능할 때만 client를 만든다.
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


# Redis를 사용할 수 없을 때 쓰는 로컬 메모리 cache 조회다.
# TTL이 지난 항목은 조회 시점에 제거한다.
def _get_memory_retrieval_cache(query_hash: str) -> RetrievalCacheLookupResult:
    entry = _RETRIEVAL_CACHE.get(query_hash)
    if entry is None:
        return {"hit": False}

    documents, expires_at = entry
    if time.time() > expires_at:
        _RETRIEVAL_CACHE.pop(query_hash, None)
        return {"hit": False}

    return {"hit": True, "documents": documents}


# 로컬 메모리 cache에 retrieved_documents와 만료 시각을 함께 저장한다.
def _set_memory_retrieval_cache(query_hash: str, documents: list[dict], ttl: int) -> None:
    _RETRIEVAL_CACHE[query_hash] = (documents, time.time() + ttl)


# retrieval cache 조회 순서: Redis -> memory fallback.
# cache hit이어도 이후 answer generation/safety는 동일하게 실행된다.
def get_cached_retrieval(query_hash: str) -> RetrievalCacheLookupResult:
    client = _redis_client()
    if client is not None:
        try:
            cached_json = client.get(_cache_key(query_hash, namespace="retrieval"))
            if cached_json is not None:
                return {"hit": True, "documents": json.loads(cached_json)}
        except Exception:
            pass

    return _get_memory_retrieval_cache(query_hash)


# retrieval cache 저장 순서: Redis setex -> 실패 시 memory fallback.
# ttl은 검색 결과를 얼마나 오래 재사용할지 결정한다.
def set_cached_retrieval(query_hash: str, documents: list[dict], ttl: int = 3600) -> dict[str, object]:
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

