from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data.prompts.chatbot.bug_prompt import BUG_AGENT_PROMPT
from data.prompts.chatbot.faq_prompt import FAQ_AGENT_PROMPT
from data.prompts.chatbot.payment_prompt import PAYMENT_AGENT_PROMPT
from chatbot.tools.db_tools import collect_user_payment_context, read_gacha_logs, read_item_delivery_logs


@dataclass(frozen=True)
class AgentPolicy:
    name: str
    system_prompt: str
    tools: list[Any]


PAYMENT_POLICY = AgentPolicy(
    name="payment_agent",
    system_prompt=PAYMENT_AGENT_PROMPT,
    tools=[collect_user_payment_context],
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
