from __future__ import annotations

import os

try:
    from rootsetting import ensure_project_root_on_path
except ModuleNotFoundError:
    from runners.rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from chatbot.graph.workflow import graph


def build_state(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: str = "seed-user",
    session_id: str = "seed-session",
    source_type: str = "chatbot",
    previous_messages: list[dict[str, str]] | None = None,
) -> dict:
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
        "turn_count": len([m for m in messages if m.get("role") == "user"]),
    }


def _last_message_text(result: dict) -> str:
    if result.get("final_text"):
        return str(result["final_text"])
    if result.get("draft_text"):
        return str(result["draft_text"])
    messages = result.get("messages", [])
    if not messages:
        return ""
    last_message = messages[-1]
    content = last_message.get("content", "") if isinstance(last_message, dict) else getattr(last_message, "content", "")
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def run(
    ticket_id: int,
    user_message: str,
    account_id: int | None = None,
    user_id: str = "seed-user",
    session_id: str = "seed-session",
    source_type: str = "chatbot",
) -> str:
    result = graph.invoke(build_state(
        ticket_id=ticket_id,
        user_message=user_message,
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        source_type=source_type,
    ))
    if os.getenv("CHATBOT_DEBUG_ROUTING", "").lower() in ("1", "true", "yes"):
        print("[routing_debug]")
        print(f"category: {result.get('category')}")
        print(f"routing_target: {result.get('routing_target')}")
        print(f"classification_method: {result.get('classification_method')}")
        print(f"classification_reason: {result.get('classification_reason')}")
    return _last_message_text(result)


def run_multiturn_demo() -> list[str]:
    """Run a two-turn smoke scenario while preserving prior messages."""
    history: list[dict[str, str]] = []
    answers: list[str] = []
    turns = [
        (1001, "결제했는데 아이템이 안 들어왔어요."),
        (1001, "방금 말한 결제 건은 환불도 가능한가요?"),
    ]

    for ticket_id, user_message in turns:
        state = build_state(
            ticket_id=ticket_id,
            user_message=user_message,
            account_id=101,
            previous_messages=history,
        )
        result = graph.invoke(state)
        answers.append(_last_message_text(result))
        history = result.get("messages", history)
    return answers


def main() -> None:
    from data.seed_payload import SEED_QA_TICKETS

    ticket = SEED_QA_TICKETS[0]
    answer = run(
        ticket_id=ticket["ticket_id"],
        user_message=ticket["raw_content"],
        account_id=ticket["account_id"],
    )
    print(f"[ticket_id={ticket['ticket_id']}]")
    print(f"문의: {ticket['raw_content']}")
    print(f"\n답변:\n{answer}")


if __name__ == "__main__":
    main()
