from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chatbot.prompts.bug_prompt import BUG_AGENT_PROMPT
from chatbot.prompts.faq_prompt import FAQ_AGENT_PROMPT
from chatbot.prompts.payment_prompt import PAYMENT_AGENT_PROMPT
from chatbot.tools.registry import BUG_TOOLS, FAQ_TOOLS, PAYMENT_TOOLS


@dataclass(frozen=True)
class AgentPolicy:
    name: str
    system_prompt: str
    tools: list[Any]


PAYMENT_POLICY = AgentPolicy(
    name="payment_agent",
    system_prompt=PAYMENT_AGENT_PROMPT,
    tools=PAYMENT_TOOLS,
)

FAQ_POLICY = AgentPolicy(
    name="faq_agent",
    system_prompt=FAQ_AGENT_PROMPT,
    tools=FAQ_TOOLS,
)

BUG_POLICY = AgentPolicy(
    name="bug_agent",
    system_prompt=BUG_AGENT_PROMPT,
    tools=BUG_TOOLS,
)

AGENT_POLICIES = {
    PAYMENT_POLICY.name: PAYMENT_POLICY,
    FAQ_POLICY.name: FAQ_POLICY,
    BUG_POLICY.name: BUG_POLICY,
}
