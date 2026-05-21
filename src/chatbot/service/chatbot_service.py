from __future__ import annotations

import os
from typing import Any

from chatbot.observability.logger import log_operator_summary

def build_state(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: str = "seed-user",
    session_id: str = "seed-session",
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
        "ticket_id": ticket_id,
        "category": "",
        "routing_target": "",
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
    user_id: str = "seed-user",
    session_id: str = "seed-session",
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
    result = graph.invoke(state)

    if os.getenv("CHATBOT_DEBUG_ROUTING", "").lower() in ("1", "true", "yes"):
        print("[routing_debug]")
        print(f"category: {result.get('category')}")
        print(f"routing_target: {result.get('routing_target')}")
        print(f"classification_method: {result.get('classification_method')}")
        print(f"classification_reason: {result.get('classification_reason')}")

    answer = last_message_text(result)
    log_operator_summary(
        ticket_id=ticket_id,
        session_id=session_id,
        user_id=user_id,
        raw_query=user_message,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        safety_action=result.get("safety_action"),
        final_text=answer,
        notification_result=result.get("notification_result"),
    )

    return {
        "answer": answer,
        "state": result,
    }


def stream_chatbot(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: str = "seed-user",
    session_id: str = "seed-session",
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

    for chunk in graph.stream(state, stream_mode="updates"):
        for node_update in chunk.values():
            result.update(node_update)

    answer = last_message_text(result)
    log_operator_summary(
        ticket_id=ticket_id,
        session_id=session_id,
        user_id=user_id,
        raw_query=user_message,
        category=result.get("category"),
        routing_target=result.get("routing_target"),
        safety_action=result.get("safety_action"),
        final_text=answer,
        notification_result=result.get("notification_result"),
    )

    return {
        "answer": answer,
        "state": result,
        "input_state": state,
    }
