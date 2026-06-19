from __future__ import annotations

from chatbot.service.multiturn_service import (
    ConversationTurn,
    _extract_ai_response,
    _extract_user_query,
    _fallback_summary,
    _session_base,
    _turns_to_messages,
)


def test_extract_user_and_ai_text_from_ticket_transcript() -> None:
    raw_query = "User: 결제했는데 아이템이 안 들어왔어요\nAI: 지급 로그를 확인해드릴게요."

    assert _extract_user_query(raw_query) == "결제했는데 아이템이 안 들어왔어요"
    assert _extract_ai_response(raw_query) == "지급 로그를 확인해드릴게요."


def test_session_base_removes_turn_suffix() -> None:
    assert _session_base("chatbot-abc-3") == "chatbot-abc"
    assert _session_base("chatbot-abc") == "chatbot-abc"


def test_turns_to_messages_keeps_user_assistant_order() -> None:
    turns = [
        ConversationTurn(ticket_id=1, user_text="첫 질문", assistant_text="첫 답변"),
        ConversationTurn(ticket_id=2, user_text="두 번째 질문", assistant_text=None),
    ]

    assert _turns_to_messages(turns) == [
        {"role": "user", "content": "첫 질문"},
        {"role": "assistant", "content": "첫 답변"},
        {"role": "user", "content": "두 번째 질문"},
    ]


def test_fallback_summary_clips_old_turns() -> None:
    turns = [
        ConversationTurn(ticket_id=1, user_text="결제 문의", assistant_text="결제 상태를 확인했습니다."),
        ConversationTurn(ticket_id=2, user_text="환불 문의", assistant_text="환불은 운영 검토가 필요합니다."),
    ]

    summary = _fallback_summary(turns)

    assert "이전 대화 요약:" in summary
    assert "결제 문의" in summary
    assert "환불 문의" in summary
