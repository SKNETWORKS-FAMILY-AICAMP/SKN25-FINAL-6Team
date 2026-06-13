from __future__ import annotations

from chatbot.memory.chat_history import build_compact_history, trim_recent_turns


def test_trim_recent_turns_keeps_latest_three_user_turns() -> None:
    history = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "user", "content": "turn 3"},
        {"role": "assistant", "content": "answer 3"},
        {"role": "user", "content": "turn 4"},
        {"role": "assistant", "content": "answer 4"},
    ]

    result = trim_recent_turns(history)

    assert [message["content"] for message in result] == [
        "turn 2",
        "answer 2",
        "turn 3",
        "answer 3",
        "turn 4",
        "answer 4",
    ]


def test_build_compact_history_prepends_summary_without_dropping_latest_turn() -> None:
    history = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "latest question"},
    ]

    result = build_compact_history(
        history,
        conversation_summary="사용자는 결제 상품 미수령을 문의했고 주문 번호는 아직 제공하지 않았다.",
        max_turns=1,
    )

    assert result[0] == {
        "role": "system",
        "content": "Conversation summary:\n사용자는 결제 상품 미수령을 문의했고 주문 번호는 아직 제공하지 않았다.",
    }
    assert result[-1] == {"role": "user", "content": "latest question"}
