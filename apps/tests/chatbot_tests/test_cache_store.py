from __future__ import annotations

import time

from chatbot.retrieval import cache_store


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
    """Reset env-driven cache state between tests."""
    monkeypatch.delenv("REDIS_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CACHE_KEY_PREFIX", raising=False)
    cache_store.clear_cache_for_tests()


def test_memory_cache_is_used_when_redis_is_disabled(monkeypatch) -> None:
    """REDIS_ENABLED=false should preserve the existing in-memory behavior."""
    _reset_cache(monkeypatch)
    monkeypatch.setenv("REDIS_ENABLED", "false")

    assert cache_store.get_cached_answer("query-a") == {"hit": False}

    result = cache_store.set_cached_answer("query-a", "cached answer", ttl=60)

    assert result["backend"] == "memory"
    assert cache_store.get_cached_answer("query-a") == {
        "hit": True,
        "answer": "cached answer",
    }


def test_memory_cache_expires_by_ttl(monkeypatch) -> None:
    """Expired in-memory entries should be treated as cache misses."""
    _reset_cache(monkeypatch)

    cache_store.set_cached_answer("query-a", "cached answer", ttl=0)

    assert cache_store.get_cached_answer("query-a") == {"hit": False}


def test_clear_cache_for_tests_resets_memory_cache(monkeypatch) -> None:
    """clear_cache_for_tests should isolate cache state across tests."""
    _reset_cache(monkeypatch)
    cache_store.set_cached_answer("query-a", "cached answer", ttl=60)

    cache_store.clear_cache_for_tests()

    assert cache_store.get_cached_answer("query-a") == {"hit": False}


def test_redis_cache_is_used_when_enabled(monkeypatch) -> None:
    """When Redis is enabled and healthy, cache_store should use Redis keys."""
    _reset_cache(monkeypatch)
    fake_redis = FakeRedis()
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("CACHE_KEY_PREFIX", "gameops")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: fake_redis)

    result = cache_store.set_cached_answer("query-a", "cached answer", ttl=60)

    assert result["backend"] == "redis"
    assert "gameops:faq:answer:v1:query-a" in fake_redis.values
    assert cache_store.get_cached_answer("query-a") == {
        "hit": True,
        "answer": "cached answer",
    }


def test_redis_failure_falls_back_to_memory_cache(monkeypatch) -> None:
    """Redis write failures should fall back to memory instead of raising."""
    _reset_cache(monkeypatch)
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: FailingRedis())

    result = cache_store.set_cached_answer("query-a", "cached answer", ttl=60)

    assert result["backend"] == "memory"
    assert cache_store.get_cached_answer("query-a") == {
        "hit": True,
        "answer": "cached answer",
    }


def test_memory_retrieval_cache_is_used_when_redis_is_disabled(monkeypatch) -> None:
    """Retrieved documents should be cacheable without storing final answers."""
    _reset_cache(monkeypatch)
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "memory"
    assert result["document_count"] == 1
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }


def test_redis_retrieval_cache_uses_separate_namespace(monkeypatch) -> None:
    """Retrieval evidence cache should not collide with final answer cache keys."""
    _reset_cache(monkeypatch)
    fake_redis = FakeRedis()
    documents = [{"chunk_id": "chunk-1", "chunk_text": "evidence"}]
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("CACHE_KEY_PREFIX", "gameops")
    monkeypatch.setattr(cache_store, "_redis_client", lambda: fake_redis)

    result = cache_store.set_cached_retrieval("query-a", documents, ttl=60)

    assert result["backend"] == "redis"
    assert "gameops:faq:retrieval:v1:query-a" in fake_redis.values
    assert cache_store.get_cached_retrieval("query-a") == {
        "hit": True,
        "documents": documents,
    }
