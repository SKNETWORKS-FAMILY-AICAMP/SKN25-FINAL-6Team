from __future__ import annotations

try:
    from rootsetting import ensure_project_root_on_path
except ModuleNotFoundError:
    from runners.rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from chatbot.agent import agent


def _last_message_text(result: dict) -> str:
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
    result = agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    f"ticket_id={ticket_id}\n"
                    f"account_id={account_id}\n"
                    f"source_type={source_type}\n\n"
                    f"Customer inquiry:\n{user_message}"
                ),
            }
        ],
        "user_id": user_id,
        "session_id": session_id,
        "account_id": account_id,
        "source_type": source_type,
        "raw_content": user_message,
        "cleaned_content": user_message,
        "ticket_id": ticket_id,
        "category": "",
        "routing_target": "",
        "risk_level": "",
        "sentiment": "",
        "draft_id": None,
        "answer_draft": None,
        "safety_passed": None,
        "retry_count": 0,
    })
    return _last_message_text(result)


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
