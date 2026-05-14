from deepagents import create_deep_agent


def load_observability_context(ticket_id: int | None = None) -> str:
    """Load analysis, safety, and final outcome data for STEP3."""
    return f"ticket_id={ticket_id}"


agent = create_deep_agent(
    model="openai:gpt-5.4",
    tools=[load_observability_context],
    system_prompt=(
        "You are the dashboard agent for STEP3 observability. "
        "Summarize operational insights, metric trends, and alert conditions. "
        "Do not draft replies or handle approval gates."
    ),
)
