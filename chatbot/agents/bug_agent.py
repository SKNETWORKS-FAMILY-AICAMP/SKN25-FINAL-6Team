from __future__ import annotations

import json

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import (
    read_gacha_logs,
    read_item_delivery_logs,
    write_answer_draft,
    write_evidence_docs,
)


def bug_agent_node(state: ChatbotState) -> dict:
    ticket_id = state.get("ticket_id") or 0
    account_id = state.get("account_id")

    gacha_logs = read_gacha_logs.invoke({"account_id": account_id}) if account_id is not None else "[]"
    delivery_logs = (
        read_item_delivery_logs.invoke({"account_id": account_id})
        if account_id is not None
        else "[]"
    )
    answer = (
        "인게임 로그와 지급 기록을 확인했습니다. "
        "재현 조건 또는 지급 여부 확인이 필요한 경우 운영자 검토로 이어질 수 있습니다."
    )

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": answer},
    })
    draft_id = json.loads(draft_result).get("draft_id")
    write_evidence_docs.invoke({
        "payload": {
            "draft_id": draft_id,
            "source": "gacha_logs/item_delivery_logs",
            "gacha_logs": gacha_logs,
            "item_delivery_logs": delivery_logs,
        },
    })

    return {
        "answer_draft": answer,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
    }
