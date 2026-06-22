from __future__ import annotations

import os
from unittest.mock import Mock

from common.observability.langfuse import configure_langfuse, record_current_scores


def test_configure_langfuse_reads_app_specific_env(monkeypatch) -> None:
    monkeypatch.setenv("CS_AUTO_LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("CS_AUTO_LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("CS_AUTO_LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("CS_AUTO_LANGFUSE_HOST", "https://cloud.langfuse.com")
    monkeypatch.setenv("CS_AUTO_LANGFUSE_PROJECT", "cs-auto")

    config = configure_langfuse("cs-auto", default_tags=["cs-auto", "api"])

    assert config["app_name"] == "cs-auto"
    assert config["project"] == "cs-auto"
    assert config["public_key"] == "pk-test"
    assert config["secret_key"] == "sk-test"
    assert config["host"] == "https://cloud.langfuse.com"
    assert config["default_tags"] == ["cs-auto", "api"]
    assert isinstance(config["enabled"], bool)
    assert isinstance(config["sdk_available"], bool)
    assert os.environ["LANGFUSE_ENABLED"] in {"true", "false"}


def test_record_current_scores_uses_observation_score_api(monkeypatch) -> None:
    score_current_observation = Mock()
    fake_context = type(
        "FakeContext",
        (),
        {"score_current_observation": score_current_observation},
    )()
    monkeypatch.setattr("common.observability.langfuse._langfuse_context", lambda: fake_context)

    record_current_scores(
        {
            "factuality_score": 0.8,
            "review_required": True,
            "ignored_text": "skip",
        },
        comments={"review_required": "manual review"},
    )

    assert score_current_observation.call_count == 2
    calls = score_current_observation.call_args_list
    assert calls[0].kwargs["name"] == "factuality_score"
    assert calls[0].kwargs["value"] == 0.8
    assert calls[1].kwargs["name"] == "review_required"
    assert calls[1].kwargs["value"] == 1.0
    assert calls[1].kwargs["comment"] == "manual review"
