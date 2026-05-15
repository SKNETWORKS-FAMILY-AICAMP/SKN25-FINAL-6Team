from __future__ import annotations

from copy import deepcopy
from typing import Any


SEED_COMMUNITY_USERS: list[dict[str, Any]] = [
    {
        "table": "community_users",
        "user_id": 1,
        "email": "user1@game.com",
        "nickname": "FireMage",
        "user_status": "active",
        "last_login_at": "2026-05-11T22:10:00",
    }
]

SEED_GAME_ACCOUNTS: list[dict[str, Any]] = [
    {
        "table": "game_accounts",
        "account_id": 101,
        "user_id": 1,
        "game_name": "genshin impact",
        "uid": "8123456",
        "server_region": "KR",
        "progression_level": 57,
        "account_status": "active",
    }
]

SEED_QA_TICKETS: list[dict[str, Any]] = [
    {
        "table": "QA_ticket",
        "ticket_id": 1001,
        "user_id": 1,
        "account_id": 101,
        "title": "Payment completed but item was not delivered",
        "raw_content": "Payment is complete, but the item did not arrive.",
        "source_type": "community",
        "responder_type": "AI",
        "status": "open",
        "inquiry_created_at": "2026-05-11T10:00:00",
    }
]

SEED_OPERATION_LOGS: dict[str, list[dict[str, Any]]] = {
    "payments": [
        {
            "payment_id": 7001,
            "account_id": 101,
            "product_name": "starter package",
            "product_type": "package",
            "amount": 9900,
            "currency": "KRW",
            "payment_method": "card",
            "payment_status": "success",
            "transaction_id": "TXN12345",
            "paid_at": "2026-05-11T09:55:00",
        }
    ],
    "refunds": [
        {
            "refund_id": 9501,
            "payment_id": 7001,
            "refund_status": "pending",
            "refund_reason": "item not delivered",
            "requested_at": "2026-05-11T10:20:00",
            "processed_at": None,
        }
    ],
    "item_delivery_logs": [
        {
            "delivery_id": 8001,
            "payment_id": 7001,
            "account_id": 101,
            "source_type": "payment_reward",
            "item_name": "starter package box",
            "quantity": 1,
            "delivery_status": "fail",
            "expected_at": "2026-05-11T10:01:00",
            "delivered_at": None,
        }
    ],
    "gacha_logs": [],
}

SEED_DOCUMENTS: list[dict[str, Any]] = [
    {
        "table": "documents",
        "documents_id": "FAQ-101",
        "source_type": "FAQ",
        "category": "payment",
        "title": "Payment reward delivery guide",
        "raw_content": (
            "Payment rewards may take up to 5 minutes to be delivered after a successful purchase. "
            "If payment succeeds but the item is still missing, check the delivery log first."
        ),
        "source_url": "https://docs.game.com/faq/payment-reward-delivery",
        "published_at": "2026-05-01T10:00:00",
        "updated_at": "2026-05-01T11:00:00",
    },
    {
        "table": "documents",
        "documents_id": "POLICY-204",
        "source_type": "POLICY",
        "category": "payment",
        "title": "Manual review policy for failed item delivery",
        "raw_content": (
            "If payment succeeds but the delivery log remains failed, operators must review the "
            "delivery record before refund or re-delivery."
        ),
        "source_url": "https://docs.game.com/policy/manual-review-failed-delivery",
        "published_at": "2026-05-02T09:00:00",
        "updated_at": "2026-05-02T09:30:00",
    },
    {
        "table": "documents",
        "documents_id": "NOTICE-330",
        "source_type": "NOTICE",
        "category": "payment",
        "title": "Escalation for payment delivery incidents",
        "raw_content": (
            "Repeated payment delivery incidents should be routed to urgent review when the player "
            "is missing a paid item."
        ),
        "source_url": "https://docs.game.com/notice/payment-delivery-escalation",
        "published_at": "2026-05-03T09:00:00",
        "updated_at": "2026-05-03T09:30:00",
    },
]

SEED_DOCUMENT_CHUNKS: list[dict[str, Any]] = [
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-101-1",
        "document_id": "FAQ-101",
        "chunk_text": "Payment rewards may take up to 5 minutes to be delivered after a successful purchase.",
        "chunk_order": 1,
        "token_count": 14,
        "created_at": "2026-05-01T10:05:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-101-2",
        "document_id": "FAQ-101",
        "chunk_text": "If the item does not arrive after payment success, check delivery records before additional action.",
        "chunk_order": 2,
        "token_count": 15,
        "created_at": "2026-05-01T10:05:30",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "POLICY-204-1",
        "document_id": "POLICY-204",
        "chunk_text": "If payment succeeds but the delivery log remains failed, operators must review the delivery record before refund or re-delivery.",
        "chunk_order": 1,
        "token_count": 19,
        "created_at": "2026-05-02T09:05:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "NOTICE-330-1",
        "document_id": "NOTICE-330",
        "chunk_text": "Repeated payment delivery incidents should be routed to urgent review when the player is missing a paid item.",
        "chunk_order": 1,
        "token_count": 16,
        "created_at": "2026-05-03T09:10:00",
    },
]

SEED_DOCUMENT_EMBEDDINGS: list[dict[str, Any]] = [
    {
        "table": "documents_embeddings",
        "embedding_id": "FAQ-101-1-E",
        "chunk_id": "FAQ-101-1",
        "embedding_vector": [0.123, 0.532, 0.287, 0.441],
        "embedding_model": "bge-m3",
        "source_type": "FAQ",
        "category": "payment",
        "created_at": "2026-05-01T10:06:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "FAQ-101-2-E",
        "chunk_id": "FAQ-101-2",
        "embedding_vector": [0.231, 0.884, 0.118, 0.367],
        "embedding_model": "bge-m3",
        "source_type": "FAQ",
        "category": "payment",
        "created_at": "2026-05-01T10:06:10",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "POLICY-204-1-E",
        "chunk_id": "POLICY-204-1",
        "embedding_vector": [0.912, 0.112, 0.564, 0.778],
        "embedding_model": "bge-m3",
        "source_type": "POLICY",
        "category": "payment",
        "created_at": "2026-05-02T09:06:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "NOTICE-330-1-E",
        "chunk_id": "NOTICE-330-1",
        "embedding_vector": [0.774, 0.291, 0.665, 0.509],
        "embedding_model": "bge-m3",
        "source_type": "NOTICE",
        "category": "payment",
        "created_at": "2026-05-03T09:11:00",
    },
]


def build_knowledge_base_from_vector_ddl(
    documents: list[dict[str, Any]] | None = None,
    document_chunks: list[dict[str, Any]] | None = None,
    document_embeddings: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "documents": deepcopy(documents or SEED_DOCUMENTS),
        "documents_chunks": deepcopy(document_chunks or SEED_DOCUMENT_CHUNKS),
        "documents_embeddings": deepcopy(document_embeddings or SEED_DOCUMENT_EMBEDDINGS),
    }


def _find_by_id(rows: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any]:
    for row in rows:
        if row.get(key) == value:
            return deepcopy(row)
    raise ValueError(f"Seed row not found for {key}={value!r}")


def build_account_context_from_ddl(
    qa_ticket: dict[str, Any],
    community_users: list[dict[str, Any]],
    game_accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    user = _find_by_id(community_users, "user_id", qa_ticket["user_id"])
    account = _find_by_id(game_accounts, "account_id", qa_ticket["account_id"])

    if account["user_id"] != user["user_id"]:
        raise ValueError(
            "Seed data mismatch: game_accounts.user_id does not match community_users.user_id"
        )

    return {
        "community_users": user,
        "game_accounts": account,
    }


def build_first_input_payload(
    ticket_id: int,
    qa_tickets: list[dict[str, Any]] | None = None,
    community_users: list[dict[str, Any]] | None = None,
    game_accounts: list[dict[str, Any]] | None = None,
    operation_logs: dict[str, list[dict[str, Any]]] | None = None,
    documents: list[dict[str, Any]] | None = None,
    document_chunks: list[dict[str, Any]] | None = None,
    document_embeddings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    qa_ticket_rows = qa_tickets or SEED_QA_TICKETS
    community_user_rows = community_users or SEED_COMMUNITY_USERS
    game_account_rows = game_accounts or SEED_GAME_ACCOUNTS
    operation_log_rows = operation_logs or SEED_OPERATION_LOGS

    qa_ticket = _find_by_id(qa_ticket_rows, "ticket_id", ticket_id)
    account_context = build_account_context_from_ddl(
        qa_ticket=qa_ticket,
        community_users=community_user_rows,
        game_accounts=game_account_rows,
    )
    knowledge_base = build_knowledge_base_from_vector_ddl(
        documents=documents,
        document_chunks=document_chunks,
        document_embeddings=document_embeddings,
    )

    return {
        "qa_ticket": qa_ticket,
        "account_context": account_context,
        "operation_logs": deepcopy(operation_log_rows),
        "knowledge_base": knowledge_base,
    }


FIRST_INPUT_PAYLOAD: dict[str, Any] = build_first_input_payload(ticket_id=1001)

SEED_DASHBOARD_INPUTS: dict[str, Any] = {
    "ticket_analysis": [
        {
            "analysis_id": 5001,
            "ticket_id": 1001,
            "user_id": 1,
            "account_id": 101,
            "category": "payment",
            "sentiment": "negative",
            "risk_level": "HIGH",
            "routing_target": "urgent_alert",
            "summary": "Payment succeeded but item delivery failed.",
            "inquiry_created_at": "2026-05-11T10:00:00",
        }
    ],
    "safety_results": [
        {
            "safety_id": 6001,
            "draft_id": 3001,
            "hallucination_score": 0.03,
            "toxicity_score": 0.0,
            "policy_violation_score": 0.01,
            "factuality_score": 0.98,
        }
    ],
    "final_outcomes": [
        {
            "ticket_id": 1001,
            "status": "closed",
            "approval_result": "human_review",
            "operator_action": "manual_delivery_review",
        }
    ],
}

SEED_METRICS: dict[str, Any] = {
    "window": "daily",
    "payment_delivery_failure_rate": 0.18,
    "high_risk_ticket_count": 1,
    "repeat_inquiry_rate": 0.22,
    "operator_edit_rate": 0.31,
    "answer_approval_rate": 0.69,
    "negative_sentiment_trend": "increasing",
}

SEED_INSIGHT: dict[str, Any] = {
    "table": "insight",
    "insight_id": 11001,
    "user_id": 1,
    "ticket_id": 1001,
    "account_id": 101,
    "content_summary": "Repeated payment delivery failure inquiries are increasing.",
    "category": "payment",
    "sentiment": "negative",
    "risk_level": "HIGH",
    "pattern_risk_level": "CRITICAL",
    "inquiry_created_at": "2026-05-11T10:00:00",
}

SEED_ALERT: dict[str, Any] = {
    "metric_name": "payment_delivery_failure_rate",
    "current_value": 0.18,
    "threshold": 0.1,
    "alert_required": True,
    "channels": ["Slack", "Discord"],
    "message": "Payment delivery failure rate is above threshold. Review item delivery logs.",
}


def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)
