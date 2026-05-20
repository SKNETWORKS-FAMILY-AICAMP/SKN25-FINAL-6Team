from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_core")

from chatbot.retrieval import cache_tools


def _invoke(tool, payload: dict) -> dict:
    return json.loads(tool.invoke(payload))


def setup_function() -> None:
    cache_tools._CACHE.clear()


def test_get_cache_returns_miss_for_unknown_key() -> None:
    result = _invoke(cache_tools.get_cache, {"query_hash": "unknown"})

    assert result == {"hit": False}


def test_set_then_get_cache_returns_hit() -> None:
    set_result = _invoke(
        cache_tools.set_cache,
        {"query_hash": "faq:event_reward", "answer": "이벤트 보상은 순차 지급됩니다."},
    )
    result = _invoke(cache_tools.get_cache, {"query_hash": "faq:event_reward"})

    assert set_result["status"] == "ok"
    assert result == {"hit": True, "answer": "이벤트 보상은 순차 지급됩니다."}


def test_expired_cache_returns_miss_and_removes_entry() -> None:
    _invoke(
        cache_tools.set_cache,
        {"query_hash": "faq:expired", "answer": "만료될 답변입니다.", "ttl": -1},
    )
    result = _invoke(cache_tools.get_cache, {"query_hash": "faq:expired"})

    assert result == {"hit": False}
    assert "faq:expired" not in cache_tools._CACHE
