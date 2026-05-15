from __future__ import annotations

from copy import deepcopy
from typing import Any


SEED_COMMUNITY_USERS: list[dict[str, Any]] = [
    {
        "table": "community_users",
        "user_id": 1,
        "email": "user1@game.com",
        "nickname": "불꽃술사",
        "user_status": "active",
        "last_login_at": "2026-05-11T22:10:00",
    }
]

SEED_GAME_ACCOUNTS: list[dict[str, Any]] = [
    {
        "table": "game_accounts",
        "account_id": 101,
        "user_id": 1,
        "game_name": "원신",
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
        "title": "결제는 완료됐는데 아이템이 지급되지 않았어요",
        "raw_content": "결제는 정상적으로 완료됐는데 구매한 스타터 패키지 아이템이 아직 들어오지 않았습니다.",
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
            "product_name": "스타터 패키지",
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
            "refund_reason": "아이템 미지급",
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
            "item_name": "스타터 패키지 상자",
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
        "title": "결제 보상 지급 안내",
        "raw_content": "결제 보상은 구매 성공 후 최대 5분 이내에 지급될 수 있습니다.",
        "source_url": "https://docs.game.com/faq/payment-reward-delivery",
        "published_at": "2026-05-01T10:00:00",
        "updated_at": "2026-05-01T11:00:00",
    },
    {
        "table": "documents",
        "documents_id": "FAQ-102",
        "source_type": "FAQ",
        "category": "payment",
        "title": "결제 후 아이템 미지급 확인 절차",
        "raw_content": "결제 성공 후에도 아이템이 보이지 않으면 우선 지급 로그와 우편함을 확인해야 합니다.",
        "source_url": "https://docs.game.com/faq/payment-missing-item",
        "published_at": "2026-05-01T12:00:00",
        "updated_at": "2026-05-01T12:30:00",
    },
    {
        "table": "documents",
        "documents_id": "POLICY-204",
        "source_type": "POLICY",
        "category": "payment",
        "title": "아이템 지급 실패 수동 검토 정책",
        "raw_content": "결제는 성공했지만 지급 로그가 실패 상태라면 운영자는 환불이나 재지급 전에 지급 기록을 수동 검토해야 합니다.",
        "source_url": "https://docs.game.com/policy/manual-review-failed-delivery",
        "published_at": "2026-05-02T09:00:00",
        "updated_at": "2026-05-02T09:30:00",
    },
    {
        "table": "documents",
        "documents_id": "NOTICE-330",
        "source_type": "NOTICE",
        "category": "payment",
        "title": "결제 지급 이슈 긴급 대응 공지",
        "raw_content": "유료 아이템 미지급이 반복되는 경우에는 해당 문의를 긴급 검토 대상으로 분류해야 합니다.",
        "source_url": "https://docs.game.com/notice/payment-delivery-escalation",
        "published_at": "2026-05-03T09:00:00",
        "updated_at": "2026-05-03T09:30:00",
    },
    {
        "table": "documents",
        "documents_id": "FAQ-201",
        "source_type": "FAQ",
        "category": "refund",
        "title": "중복 결제 환불 안내",
        "raw_content": "중복 결제가 확인되면 영업일 기준 3일 이내에 환불 절차가 진행됩니다.",
        "source_url": "https://docs.game.com/faq/duplicate-payment-refund",
        "published_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:20:00",
    },
    {
        "table": "documents",
        "documents_id": "POLICY-205",
        "source_type": "POLICY",
        "category": "refund",
        "title": "환불 승인 전 검토 기준",
        "raw_content": "환불 승인 전에는 결제 성공 여부와 지급 완료 여부를 함께 검토해야 합니다.",
        "source_url": "https://docs.game.com/policy/refund-review-checklist",
        "published_at": "2026-05-04T11:00:00",
        "updated_at": "2026-05-04T11:15:00",
    },
    {
        "table": "documents",
        "documents_id": "NOTICE-410",
        "source_type": "NOTICE",
        "category": "event",
        "title": "이벤트 보상 순차 지급 안내",
        "raw_content": "이벤트 보상은 대상자 확인 후 순차적으로 지급되며 즉시 반영되지 않을 수 있습니다.",
        "source_url": "https://docs.game.com/notice/event-reward-delay",
        "published_at": "2026-05-05T09:00:00",
        "updated_at": "2026-05-05T09:10:00",
    },
    {
        "table": "documents",
        "documents_id": "FAQ-301",
        "source_type": "FAQ",
        "category": "gacha",
        "title": "가챠 획득 내역 확인 방법",
        "raw_content": "가챠 결과는 기록 메뉴에서 확인할 수 있으며 반영까지 수 분이 소요될 수 있습니다.",
        "source_url": "https://docs.game.com/faq/gacha-history",
        "published_at": "2026-05-06T13:00:00",
        "updated_at": "2026-05-06T13:30:00",
    },
    {
        "table": "documents",
        "documents_id": "POLICY-501",
        "source_type": "POLICY",
        "category": "account",
        "title": "계정 이상 이용 제한 정책",
        "raw_content": "비정상 결제나 악용 정황이 확인되면 계정 상태를 제한으로 변경할 수 있습니다.",
        "source_url": "https://docs.game.com/policy/account-restriction",
        "published_at": "2026-05-07T08:00:00",
        "updated_at": "2026-05-07T08:20:00",
    },
    {
        "table": "documents",
        "documents_id": "NOTICE-520",
        "source_type": "NOTICE",
        "category": "system",
        "title": "지급 로그 지연 점검 공지",
        "raw_content": "일시적인 시스템 지연으로 지급 로그 반영이 늦어질 수 있으며 순차 정상화 중입니다.",
        "source_url": "https://docs.game.com/notice/delivery-log-delay",
        "published_at": "2026-05-08T15:00:00",
        "updated_at": "2026-05-08T15:30:00",
    },
]

SEED_DOCUMENT_CHUNKS: list[dict[str, Any]] = [
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-101-1",
        "document_id": "FAQ-101",
        "chunk_text": "결제 보상은 구매 성공 후 최대 5분 이내에 지급될 수 있습니다.",
        "chunk_order": 1,
        "token_count": 14,
        "created_at": "2026-05-01T10:05:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-102-1",
        "document_id": "FAQ-102",
        "chunk_text": "결제 성공 후에도 아이템이 보이지 않으면 우편함과 지급 로그를 먼저 확인해야 합니다.",
        "chunk_order": 1,
        "token_count": 15,
        "created_at": "2026-05-01T12:35:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "POLICY-204-1",
        "document_id": "POLICY-204",
        "chunk_text": "지급 로그가 실패 상태라면 운영자는 환불이나 재지급 전에 지급 기록을 수동 검토해야 합니다.",
        "chunk_order": 1,
        "token_count": 18,
        "created_at": "2026-05-02T09:05:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "NOTICE-330-1",
        "document_id": "NOTICE-330",
        "chunk_text": "유료 아이템 미지급이 반복되면 해당 문의는 긴급 검토 대상으로 라우팅해야 합니다.",
        "chunk_order": 1,
        "token_count": 16,
        "created_at": "2026-05-03T09:10:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-201-1",
        "document_id": "FAQ-201",
        "chunk_text": "중복 결제가 확인되면 영업일 기준 3일 이내에 환불 절차가 진행됩니다.",
        "chunk_order": 1,
        "token_count": 14,
        "created_at": "2026-05-04T10:25:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "POLICY-205-1",
        "document_id": "POLICY-205",
        "chunk_text": "환불 승인 전에는 결제 성공 여부와 지급 완료 여부를 함께 검토해야 합니다.",
        "chunk_order": 1,
        "token_count": 14,
        "created_at": "2026-05-04T11:20:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "NOTICE-410-1",
        "document_id": "NOTICE-410",
        "chunk_text": "이벤트 보상은 대상자 확인 후 순차 지급되며 즉시 반영되지 않을 수 있습니다.",
        "chunk_order": 1,
        "token_count": 15,
        "created_at": "2026-05-05T09:15:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "FAQ-301-1",
        "document_id": "FAQ-301",
        "chunk_text": "가챠 결과는 기록 메뉴에서 확인할 수 있으며 반영까지 수 분이 소요될 수 있습니다.",
        "chunk_order": 1,
        "token_count": 16,
        "created_at": "2026-05-06T13:35:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "POLICY-501-1",
        "document_id": "POLICY-501",
        "chunk_text": "비정상 결제나 악용 정황이 확인되면 계정 상태를 제한으로 변경할 수 있습니다.",
        "chunk_order": 1,
        "token_count": 14,
        "created_at": "2026-05-07T08:25:00",
    },
    {
        "table": "documents_chunks",
        "chunk_id": "NOTICE-520-1",
        "document_id": "NOTICE-520",
        "chunk_text": "시스템 지연으로 지급 로그 반영이 늦어질 수 있으며 현재 순차 정상화 중입니다.",
        "chunk_order": 1,
        "token_count": 15,
        "created_at": "2026-05-08T15:35:00",
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
        "embedding_id": "FAQ-102-1-E",
        "chunk_id": "FAQ-102-1",
        "embedding_vector": [0.231, 0.884, 0.118, 0.367],
        "embedding_model": "bge-m3",
        "source_type": "FAQ",
        "category": "payment",
        "created_at": "2026-05-01T12:36:00",
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
    {
        "table": "documents_embeddings",
        "embedding_id": "FAQ-201-1-E",
        "chunk_id": "FAQ-201-1",
        "embedding_vector": [0.351, 0.608, 0.472, 0.294],
        "embedding_model": "bge-m3",
        "source_type": "FAQ",
        "category": "refund",
        "created_at": "2026-05-04T10:26:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "POLICY-205-1-E",
        "chunk_id": "POLICY-205-1",
        "embedding_vector": [0.488, 0.537, 0.391, 0.622],
        "embedding_model": "bge-m3",
        "source_type": "POLICY",
        "category": "refund",
        "created_at": "2026-05-04T11:21:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "NOTICE-410-1-E",
        "chunk_id": "NOTICE-410-1",
        "embedding_vector": [0.207, 0.401, 0.815, 0.196],
        "embedding_model": "bge-m3",
        "source_type": "NOTICE",
        "category": "event",
        "created_at": "2026-05-05T09:16:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "FAQ-301-1-E",
        "chunk_id": "FAQ-301-1",
        "embedding_vector": [0.164, 0.712, 0.285, 0.463],
        "embedding_model": "bge-m3",
        "source_type": "FAQ",
        "category": "gacha",
        "created_at": "2026-05-06T13:36:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "POLICY-501-1-E",
        "chunk_id": "POLICY-501-1",
        "embedding_vector": [0.693, 0.255, 0.548, 0.337],
        "embedding_model": "bge-m3",
        "source_type": "POLICY",
        "category": "account",
        "created_at": "2026-05-07T08:26:00",
    },
    {
        "table": "documents_embeddings",
        "embedding_id": "NOTICE-520-1-E",
        "chunk_id": "NOTICE-520-1",
        "embedding_vector": [0.279, 0.482, 0.605, 0.721],
        "embedding_model": "bge-m3",
        "source_type": "NOTICE",
        "category": "system",
        "created_at": "2026-05-08T15:36:00",
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
            "summary": "결제는 성공했지만 아이템 지급이 실패한 문의다.",
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
    "content_summary": "결제 후 아이템 미지급 관련 반복 문의가 증가하고 있다.",
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
    "message": "결제 지급 실패율이 임계치를 초과했습니다. 아이템 지급 로그를 점검하세요.",
}


def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)
