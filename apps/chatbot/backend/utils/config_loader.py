from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CHATBOT_CONFIG_ROOT = Path(
    os.environ.get(
        "CHATBOT_CONFIG_DIR",
        Path(__file__).resolve().parents[4] / "data" / "chatbot",
    )
)


@lru_cache(maxsize=32)
def load_chatbot_yaml(relative_path: str) -> dict[str, Any]:
    path = CHATBOT_CONFIG_ROOT / relative_path
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Chatbot YAML must contain a mapping: {path}")
    return raw_data


def get_list_config(relative_path: str, key: str) -> tuple[str, ...]:
    value = load_chatbot_yaml(relative_path).get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Expected list[str] at {relative_path}:{key}")
    return tuple(value)


def get_text_config(relative_path: str, key: str) -> str:
    value = load_chatbot_yaml(relative_path).get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string at {relative_path}:{key}")
    return value.strip()
