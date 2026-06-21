from __future__ import annotations

import os

from common.observability.langfuse import configure_langfuse


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
