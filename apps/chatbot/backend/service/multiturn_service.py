from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from common.db.connection import db_connection


@dataclass(frozen=True)
class ConversationTurn:
    ticket_id: int
    user_text: str
    assistant_text: str | None


@dataclass(frozen=True)
class ConversationContext:
    previous_messages: list[dict[str, str]]
    conversation_summary: str | None
    turn_count: int


def build_session_context(
    *,
    session_id: int,
    user_id: int,
    account_id: int | None,
    current_ticket_id: int,
    recent_turns: int = 3,
) -> ConversationContext:
    """Build compact multi-turn context from previously answered tickets."""
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


def _extract_user_query(raw_query: str | None) -> str:
    if not raw_query:
        return ""
    marker = "\nAI: "
    text = raw_query.split(marker, 1)[0]
    if text.startswith("User: "):
        text = text[len("User: "):]
    return _clean_text(text)


def _extract_ai_response(raw_query: str | None) -> str | None:
    if not raw_query:
        return None
    marker = "\nAI: "
    idx = raw_query.find(marker)
    if idx == -1:
        return None
    return raw_query[idx + len(marker):]


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
                    t.raw_query
                FROM qa_ticket t
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
    for ticket_id, raw_query in rows:
        user_text = _extract_user_query(raw_query)
        assistant_text = _extract_ai_response(raw_query)
        if user_text:
            turns.append(
                ConversationTurn(
                    ticket_id=int(ticket_id),
                    user_text=user_text,
                    assistant_text=assistant_text,
                )
            )
    return turns


def _turns_to_messages(turns: list[ConversationTurn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.user_text})
        if turn.assistant_text:
            messages.append({"role": "assistant", "content": turn.assistant_text})
    return messages


def _summarize_older_turns(turns: list[ConversationTurn]) -> str | None:
    if not turns:
        return None

    max_turns = int(os.environ.get("CHATBOT_SUMMARY_MAX_TURNS", "12"))
    source_turns = turns[-max_turns:]
    transcript = _format_turns(source_turns)
    summary = _summarize_with_llm(transcript)
    return summary or _fallback_summary(source_turns)


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
