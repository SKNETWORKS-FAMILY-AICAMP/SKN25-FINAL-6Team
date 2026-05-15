from __future__ import annotations

from rootsetting import ensure_project_root_on_path

ensure_project_root_on_path()

from chatbot.graph.workflow import graph


def run(ticket_id: int, user_message: str, account_id: int | None = None) -> str:
    result = graph.invoke({
        "messages": [],
        "ticket_id": ticket_id,
        "user_message": user_message,
        "account_id": account_id,
        "category": "",
        "routing_target": "",
        "draft_id": None,
        "answer_draft": None,
        "safety_passed": None,
        "retry_count": 0,
    })
    return result.get("answer_draft", "")


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
