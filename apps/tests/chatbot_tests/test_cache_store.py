from __future__ import annotations

import time

from common.retrieval import cache_store


class FakeRedis:
    """Small Redis test double that supports the cache_store methods we use."""

    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        entry = self.values.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            self.values.pop(key, None)
            return None
        return value

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = (value, time.time() + ttl)


class FailingRedis:
    """Redis test double used to prove cache failures do not break chatbot flow."""

    def get(self, key: str) -> str | None:
        raise RuntimeError("redis get failed")

    def setex(self, key: str, ttl: int, value: str) -> None:
        raise RuntimeError("redis set failed")


def _reset_cache(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CACHE_KEY_PREFIX", raising=False)
    cache_store._RETRIEVAL_CACHE.clear()
    cache_store._redis_client.cache_clear()


def test_memory_retrieval_cache_is_used_when_redis_is_disabled(monkeypatch) -> None:
    _reset_cache(monkeypatch)
    monkeypatch.setenv("REDIS_ENABLED", "false")
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]

    assert cache_store.get_cached_retrieval("query-a") == {"hit": False}

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "memory"
    assert result["document_count"] == 1
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }


def test_memory_retrieval_cache_expires_by_ttl(monkeypatch) -> None:
    _reset_cache(monkeypatch)

    cache_store.set_cached_retrieval("query-a", [{"chunk_id": "chunk-1"}], ttl=-1)

    assert cache_store.get_cached_retrieval("query-a") == {"hit": False}


def test_reset_cache_helper_clears_memory_retrieval_cache(monkeypatch) -> None:
    _reset_cache(monkeypatch)
    cache_store.set_cached_retrieval("query-a", [{"chunk_id": "chunk-1"}], ttl=60)

    _reset_cache(monkeypatch)

    assert cache_store.get_cached_retrieval("query-a") == {"hit": False}


def test_redis_retrieval_cache_is_used_when_enabled(monkeypatch) -> None:
    _reset_cache(monkeypatch)
    fake_redis = FakeRedis()
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://test")
    monkeypatch.setenv("CACHE_KEY_PREFIX", "gameops")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: fake_redis)

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "redis"
    assert "gameops:faq:retrieval:v1:query-a" in fake_redis.values
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }


def test_redis_failure_falls_back_to_memory_retrieval_cache(monkeypatch) -> None:
    _reset_cache(monkeypatch)
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://test")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: FailingRedis())

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "memory"
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }


def test_redis_retrieval_cache_uses_separate_namespace(monkeypatch) -> None:
    _reset_cache(monkeypatch)
    fake_redis = FakeRedis()
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://test")
    monkeypatch.setenv("CACHE_KEY_PREFIX", "gameops")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: fake_redis)

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "redis"
    assert "gameops:faq:retrieval:v1:query-a" in fake_redis.values
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }
