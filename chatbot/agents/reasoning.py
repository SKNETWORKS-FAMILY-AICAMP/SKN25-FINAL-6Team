from __future__ import annotations

from chatbot.agents.drafting_agent import drafting_agent_node


def reasoning_agent_node(state, node_name):
    """Backward-compatible alias for the renamed drafting agent node."""
    return drafting_agent_node(state, node_name)

