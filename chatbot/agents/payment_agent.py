from __future__ import annotations

import json

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import (
    read_item_delivery_logs,
    read_payments,
    read_refunds,
    write_answer_draft,
    write_evidence_docs,
)


def payment_agent_node(state: ChatbotState) -> dict:
    ticket_id = state.get("ticket_id") or 0
    account_id = state.get("account_id")

    payments = read_payments.invoke({"account_id": account_id}) if account_id is not None else "[]"
    delivery_logs = (
        read_item_delivery_logs.invoke({"account_id": account_id})
        if account_id is not None
        else "[]"
    )

    payment_rows = json.loads(payments)
    refunds = (
        read_refunds.invoke({"payment_id": payment_rows[0]["payment_id"]})
        if payment_rows
        else "[]"
    )
    delivery_rows = json.loads(delivery_logs)

    has_failed_delivery = any(row.get("delivery_status") == "fail" for row in delivery_rows)
    answer = (
        "결제 내역과 아이템 지급 로그를 확인했습니다. "
        "결제는 성공했지만 지급 실패 기록이 있어 운영자 검토가 필요합니다."
        if has_failed_delivery
        else "결제 및 지급 기록을 확인했습니다. 확인된 정보를 기준으로 답변 초안을 생성했습니다."
    )

    draft_result = write_answer_draft.invoke({
        "payload": {"ticket_id": ticket_id, "content": answer},
    })
    draft_id = json.loads(draft_result).get("draft_id")
    write_evidence_docs.invoke({
        "payload": {
            "draft_id": draft_id,
            "source": "payments/refunds/item_delivery_logs",
            "payments": payments,
            "refunds": refunds,
            "item_delivery_logs": delivery_logs,
        },
    })

    return {
        "answer_draft": answer,
        "draft_id": draft_id,
        "retry_count": state.get("retry_count", 0),
    }
