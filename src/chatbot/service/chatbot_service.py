from __future__ import annotations

import os
from typing import Any

from chatbot.observability.logger import EVENT_NODE_COMPLETED, log_event
from chatbot.observability.langsmith import build_runnable_config, build_trace_metadata


def build_state(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    messages = list(previous_messages or [])
    messages.append({
        "role": "user",
        "content": (
            f"ticket_id={ticket_id}\n"
            f"account_id={account_id}\n"
            f"source_type={source_type}\n\n"
            f"Customer inquiry:\n{user_message}"
        ),
    })

    return {
        "messages": messages,
        "user_id": user_id,
        "session_id": session_id,
        "account_id": account_id,
        "source_type": source_type,
        "raw_query": user_message,
        "enriched_query": None,
        "ticket_id": ticket_id,
        "category": "",
        "routing_target": "",
        "classification_method": None,
        "classification_reason": None,
        "analysis_id": None,
        "draft_id": None,
        "draft_text": None,
        "final_text": None,
        "reasoning_node": None,
        "safety_passed": None,
        "safety_action": None,
        "safety_reason": None,
        "review_required": None,
        "retry_count": 0,
        "conversation_summary": None,
        "turn_count": len([message for message in messages if message.get("role") == "user"]),
    }


def last_message_text(result: dict[str, Any]) -> str:
    if result.get("final_text"):
        return str(result["final_text"])
    if result.get("draft_text"):
        return str(result["draft_text"])

    messages = result.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    content = (
        last_message.get("content", "")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def run_chatbot(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
    )
    result = graph.invoke(state, config=build_runnable_config(state, run_name="chatbot_request"))
    log_event(
        "langsmith_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_trace_metadata(result),
    )

    if os.getenv("CHATBOT_DEBUG_ROUTING", "").lower() in ("1", "true", "yes"):
        print("[routing_debug]")
        print(f"category: {result.get('category')}")
        print(f"routing_target: {result.get('routing_target')}")
        print(f"classification_method: {result.get('classification_method')}")
        print(f"classification_reason: {result.get('classification_reason')}")

    return {
        "answer": last_message_text(result),
        "state": result,
    }


def stream_chatbot(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: int = 1,
    session_id: int = 1,
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
):
    from chatbot.chains.workflow import graph

    state = build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
        previous_messages=previous_messages,
    )
    result: dict[str, Any] = {}

    for chunk in graph.stream(
        state,
        config=build_runnable_config(state, run_name="chatbot_stream_request"),
        stream_mode="updates",
    ):
        for node_name, node_update in chunk.items():
            log_event(
                EVENT_NODE_COMPLETED,
                ticket_id=ticket_id,
                session_id=session_id,
                node_name=f"stream:{node_name}",
                status="stream_update",
                metadata={"updated_keys": sorted(node_update.keys())},
            )
            result.update(node_update)

    log_event(
        "langsmith_trace_metadata_linked",
        ticket_id=ticket_id,
        session_id=session_id,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        status="ok",
        metadata=build_trace_metadata({**state, **result}),
    )

    return {
        "answer": last_message_text(result),
        "state": result,
        "input_state": state,
    }
