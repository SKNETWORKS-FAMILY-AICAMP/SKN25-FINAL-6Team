from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

from chatbot.tools.db_tools import read_gacha_logs, read_item_delivery_logs


PROMPT_ROOT = Path(
    os.environ.get(
        "CHATBOT_PROMPT_DIR",
        Path(__file__).resolve().parents[4] / "data" / "prompts" / "chatbot",
    )
)


def _load_system_prompt(prompt_name: str) -> str:
    path = PROMPT_ROOT / f"{prompt_name}.yaml"
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(raw_data, str):
        return raw_data.strip()
    if isinstance(raw_data, dict) and isinstance(raw_data.get("template"), str):
        return raw_data["template"].strip()
    raise ValueError(f"Chatbot prompt YAML must be a string or contain 'template': {path}")


PAYMENT_AGENT_PROMPT = _load_system_prompt("payment_prompt")
FAQ_AGENT_PROMPT = _load_system_prompt("faq_prompt")
BUG_AGENT_PROMPT = _load_system_prompt("bug_prompt")


@dataclass(frozen=True)
class AgentPolicy:
    name: str
    system_prompt: str
    tools: list[Any]


PAYMENT_POLICY = AgentPolicy(
    name="payment_agent",
    system_prompt=PAYMENT_AGENT_PROMPT,
    tools=[],
)

FAQ_POLICY = AgentPolicy(
    name="faq_agent",
    system_prompt=FAQ_AGENT_PROMPT,
    tools=[],
)

BUG_POLICY = AgentPolicy(
    name="bug_agent",
    system_prompt=BUG_AGENT_PROMPT,
    tools=[read_gacha_logs, read_item_delivery_logs],
)
