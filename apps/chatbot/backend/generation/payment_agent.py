from __future__ import annotations

import json
import re
from typing import Any

from langsmith import traceable

from chatbot.agent import invoke_payment_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import PAYMENT_POLICY
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.repository.operation_log_repository import collect_payment_context_by_user
from chatbot.schemas import ChatbotState


def _compact_row(row: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in row.items() if value is not None)


def _payment_context_to_evidence(context: dict[str, Any]) -> list[dict[str, Any]]:
    # 결제/환불/아이템 지급/가챠 로그를 safety와 평가에서 볼 수 있는 evidence 형식으로 변환한다.
    data = context.get("data") or {}
    evidence: list[dict[str, Any]] = []
    rank = 1
    for source_type in ("payments", "refunds", "item_delivery_logs", "gacha_logs"):
        rows = data.get(source_type) or []
        for row in rows:
            source_id = (
                row.get("payment_id")
                or row.get("refund_id")
                or row.get("delivery_id")
                or row.get("gacha_id")
                or row.get("account_id")
            )
            evidence.append(
                {
                    "chunk_id": f"{source_type}:{source_id}:{rank}",
                    "document_id": str(source_id or rank),
                    "source_type": source_type,
                    "category": "결제",
                    "title": f"{source_type} record",
                    "chunk_text": _compact_row(row),
                    "score": 1.0,
                    "retrieval_rank": rank,
                }
            )
            rank += 1
    return evidence


def _payment_context_message(context: dict[str, Any]) -> dict[str, str]:
    # payment agent가 사용자 범위 DB 근거만 보고 답하도록 system message에 DB context를 붙인다.
    return {
        "role": "system",
        "content": (
            "Payment DB context scoped to the logged-in user_id only. "
            "Use this evidence before answering payment/refund/item delivery/gacha questions. "
            "Do not use user-provided account_id or payment_id unless it appears in this context.\n\n"
            f"{json.dumps(context, ensure_ascii=False, default=str)}"
        ),
    }


ITEM_MATCH_STOPWORDS = {
    "아이템",
    "보상",
    "상자",
    "상품",
    "패키지",
    "지급",
    "미지급",
    "확인",
    "로그",
    "인벤토리",
    "알림",
    "실제",
    "어제",
    "오늘",
    "언제",
    "들어오",
    "들어온",
    "받았",
    "받은",
    "봐주",
    "해주세요",
}


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", " ", str(value or "").lower()).strip()


def _query_text_for_matching(state: ChatbotState) -> str:
    previous_messages = state.get("previous_messages") or []
    previous_text = " ".join(
        str(message.get("content") or "")
        for message in previous_messages[-4:]
        if isinstance(message, dict) and message.get("role") == "user"
    )
    return " ".join(
        str(state.get(key) or "")
        for key in ("raw_query", "masked_content", "normalized_query", "sub_category")
    ) + " " + previous_text


def _match_terms(query_text: str) -> list[str]:
    normalized = _normalize_match_text(query_text)
    terms = []
    for token in normalized.split():
        if len(token) < 2 or token in ITEM_MATCH_STOPWORDS:
            continue
        if token.endswith(("해요", "줘요", "나요", "어요")):
            continue
        terms.append(token)
    return sorted(set(terms), key=len, reverse=True)


def _is_specific_item_query(terms: list[str], query_text: str) -> bool:
    normalized = _normalize_match_text(query_text)
    has_item_signal = any(word in normalized for word in ("아이템", "보상", "상자", "패키지", "우편", "인벤토리"))
    return has_item_signal and bool(terms)


def _delivery_matches_query(row: dict[str, Any], terms: list[str], query_text: str) -> bool:
    item_name = _normalize_match_text(row.get("item_name"))
    if not item_name or not terms:
        return False

    normalized_query = _normalize_match_text(query_text)
    if item_name and item_name in normalized_query:
        return True

    item_terms = [term for term in item_name.split() if len(term) >= 2 and term not in ITEM_MATCH_STOPWORDS]
    overlap = {term for term in terms if term in item_terms or term in item_name}
    return len(overlap) >= 1 and any(len(term) >= 3 for term in overlap)


def _annotate_item_delivery_relevance(context: dict[str, Any], state: ChatbotState) -> dict[str, Any]:
    data = context.get("data")
    if not isinstance(data, dict):
        return context

    deliveries = data.get("item_delivery_logs")
    if not isinstance(deliveries, list):
        return context

    query_text = _query_text_for_matching(state)
    terms = _match_terms(query_text)
    specific_item_query = _is_specific_item_query(terms, query_text)

    relevant = []
    other = []
    for row in deliveries:
        if isinstance(row, dict) and _delivery_matches_query(row, terms, query_text):
            relevant.append(row)
        else:
            other.append(row)

    annotated = dict(context)
    annotated_data = dict(data)
    annotated_data["relevant_item_delivery_logs"] = relevant
    annotated_data["other_item_delivery_logs"] = other
    annotated["data"] = annotated_data
    annotated["item_delivery_match"] = {
        "specific_item_query": specific_item_query,
        "query_terms": terms,
        "relevant_count": len(relevant),
        "other_count": len(other),
        "instruction": (
            "If specific_item_query is true and relevant_count is 0, do not treat records in "
            "other_item_delivery_logs as the user's requested item."
        ),
    }
    return annotated


def _summarize_payment_context_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("state") or {}
    return {
        "ticket_id": state.get("ticket_id"),
        "session_id": state.get("session_id"),
        "user_id": state.get("user_id"),
        "account_id": state.get("account_id"),
        "category": state.get("category"),
        "routing_target": state.get("routing_target"),
    }


def _summarize_payment_context_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": outputs.get("status"),
        "user_id": outputs.get("user_id"),
        "account_id": outputs.get("account_id"),
        "count": outputs.get("count"),
        "counts": outputs.get("counts") or {},
        "error": outputs.get("error"),
        "error_category": outputs.get("error_category"),
    }


@traceable(
    name="collect_payment_context",
    run_type="tool",
    tags=["chatbot", "db", "payment"],
    process_inputs=_summarize_payment_context_inputs,
    process_outputs=_summarize_payment_context_outputs,
)
def _collect_payment_context(state: ChatbotState) -> dict[str, Any]:
    # 로그인된 user_id/account_id 기준으로 결제 관련 DB context를 한 번에 조회한다.
    user_id = state.get("user_id")
    if user_id is None:
        return {
            "status": "skipped",
            "reason": "missing_user_id",
            "data": {
                "accounts": [],
                "payments": [],
                "refunds": [],
                "item_delivery_logs": [],
                "gacha_logs": [],
            },
            "counts": {},
            "count": 0,
        }
    return collect_payment_context_by_user(user_id=int(user_id), account_id=state.get("account_id"))


def payment_agent_node(state: ChatbotState) -> dict:
    # 1단계: 결제 agent 시작 로그를 남기고 사용자 범위 결제 context를 수집한다.
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    payment_context = _annotate_item_delivery_relevance(_collect_payment_context(state), state)
    payment_evidence = _payment_context_to_evidence(payment_context)

    # 2단계: DB context를 message와 retrieved_documents에 추가해 agent와 safety가 같은 근거를 보게 한다.
    agent_state = dict(state)
    agent_state["payment_context"] = payment_context
    agent_state["retrieved_documents"] = payment_evidence
    messages = [
        *list(state.get("messages") or []),
        _payment_context_message(payment_context),
    ]
    agent_state["messages"] = messages
    result = invoke_payment_agent(agent_state)
    update = build_draft_update(state, result, PAYMENT_POLICY.name)
    update["payment_context"] = payment_context
    update["retrieved_documents"] = payment_evidence

    # 3단계: 생성된 초안과 근거 수를 기록하고 다음 draft_persistence 노드로 넘긴다.
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=PAYMENT_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={
            "draft_length": len(update.get("draft_text") or ""),
            "payment_context_count": payment_context.get("count"),
            "payment_evidence_count": len(payment_evidence),
        },
    )
    return update
