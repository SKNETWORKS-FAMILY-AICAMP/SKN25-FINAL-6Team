from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from common.db.connection import db_connection


# 이전 ticket 한 건을 현재 대화 context에 넣기 위한 최소 단위다.
@dataclass(frozen=True)
class ConversationTurn:
    ticket_id: int
    user_text: str
    assistant_text: str | None


# chatbot_service가 workflow state에 넣을 멀티턴 context 결과다.
@dataclass(frozen=True)
class ConversationContext:
    previous_messages: list[dict[str, str]]
    conversation_summary: str | None
    turn_count: int


# 현재 ticket 이전의 같은 session/user/account 문의를 모아 최근 대화와 과거 요약으로 나눈다.
def build_session_context(
    *,
    session_id: int,
    user_id: int,
    account_id: int | None,
    current_ticket_id: int,
    recent_turns: int = 3,
) -> ConversationContext:
    turns = _fetch_session_turns(
        session_id=session_id,
        user_id=user_id,
        account_id=account_id,
        current_ticket_id=current_ticket_id,
    )
    if not turns:
        return ConversationContext(previous_messages=[], conversation_summary=None, turn_count=0)

    recent = turns[-recent_turns:] if recent_turns > 0 else []
    older = turns[:-recent_turns] if recent_turns > 0 else turns

    return ConversationContext(
        previous_messages=_turns_to_messages(recent),
        conversation_summary=_summarize_older_turns(older),
        turn_count=len(turns),
    )


# qa_ticket과 최신 final_response를 조인해 이전 문의/답변 turn 목록을 가져온다.
def _fetch_session_turns(
    *,
    session_id: int,
    user_id: int,
    account_id: int | None,
    current_ticket_id: int,
) -> list[ConversationTurn]:
    params: list[Any] = [session_id, user_id, current_ticket_id]
    account_filter = ""
    if account_id is not None:
        account_filter = "AND t.account_id = %s"
        params.append(account_id)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    t.ticket_id,
                    t.raw_query,
                    latest_response.final_text
                FROM qa_ticket t
                LEFT JOIN LATERAL (
                    SELECT fr.final_text
                    FROM final_response fr
                    WHERE fr.ticket_id = t.ticket_id
                    ORDER BY fr.created_at DESC NULLS LAST, fr.response_id DESC
                    LIMIT 1
                ) latest_response ON TRUE
                WHERE t.session_id = %s
                  AND t.user_id = %s
                  AND t.ticket_id <> %s
                  {account_filter}
                ORDER BY t.inquiry_created_at ASC NULLS FIRST, t.ticket_id ASC
                """,
                tuple(params),
            )
            rows = cur.fetchall()

    turns: list[ConversationTurn] = []
    for ticket_id, raw_query, final_text in rows:
        user_text = _clean_text(raw_query)
        assistant_text = _clean_text(final_text) if final_text else None
        if user_text:
            turns.append(
                ConversationTurn(
                    ticket_id=int(ticket_id),
                    user_text=user_text,
                    assistant_text=assistant_text,
                )
            )
    return turns


# 최근 turn은 요약하지 않고 user/assistant message 형태로 그대로 전달한다.
def _turns_to_messages(turns: list[ConversationTurn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.user_text})
        if turn.assistant_text:
            messages.append({"role": "assistant", "content": turn.assistant_text})
    return messages


# 오래된 turn은 토큰 절감을 위해 LLM 요약을 우선 시도하고 실패하면 규칙 기반 요약으로 대체한다.
def _summarize_older_turns(turns: list[ConversationTurn]) -> str | None:
    if not turns:
        return None

    max_turns = int(os.environ.get("CHATBOT_SUMMARY_MAX_TURNS", "12"))
    source_turns = turns[-max_turns:]
    transcript = _format_turns(source_turns)
    summary = _summarize_with_llm(transcript)
    return summary or _fallback_summary(source_turns)


# 이전 대화 transcript를 짧은 한국어 요약으로 압축한다.
def _summarize_with_llm(transcript: str) -> str | None:
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        return None

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
        response = llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Summarize the previous customer support conversation in Korean. "
                        "Keep only facts useful for answering the next turn: user intent, "
                        "account/payment/bug context, prior answers, and unresolved issues. "
                        "Do not invent facts. Keep it under 700 characters."
                    ),
                },
                {"role": "user", "content": transcript},
            ]
        )
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return _clean_text(content)
    except Exception:
        return None
    return None


def _fallback_summary(turns: list[ConversationTurn]) -> str:
    lines = ["이전 대화 요약:"]
    for turn in turns:
        lines.append(f"- Q: {_clip(turn.user_text, 160)}")
        if turn.assistant_text:
            lines.append(f"  A: {_clip(turn.assistant_text, 200)}")
    return "\n".join(lines)


def _format_turns(turns: list[ConversationTurn]) -> str:
    lines: list[str] = []
    for turn in turns:
        lines.append(f"[ticket_id={turn.ticket_id}]")
        lines.append(f"User: {turn.user_text}")
        if turn.assistant_text:
            lines.append(f"Assistant: {turn.assistant_text}")
    return "\n".join(lines)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
