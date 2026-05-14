from typing import Any

from langchain.agents import create_agent


def load_ticket_context(ticket_id: int) -> str:
    """Load QA_ticket and related operational context for STEP1 routing."""
    return f"ticket_id={ticket_id}"


def load_account_context(account_id: int) -> str:
    """Load payment, refund, and delivery context for STEP1 analysis."""
    return f"account_id={account_id}"


def retrieve_policy_context(query: str) -> str:
    """Retrieve FAQ, notice, and policy context for STEP2 answer drafting."""
    return f"policy_query={query}"


def build_operation_agent() -> Any:
    return create_agent(
        model="openai:gpt-5.4",
        tools=[load_ticket_context, load_account_context, retrieve_policy_context],
        system_prompt=(
            "You are the operation agent for STEP1 and STEP2. "
            "First analyze the inquiry type and risk, then generate a draft answer. "
            "Use operational context, payment logs, delivery logs, and policy retrieval. "
            "Prepare output for approval and human review. "
            "Do not perform observability or metric aggregation."
        ),
    )


agent = build_operation_agent()
