from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from chatbot.agent import invoke_payment_agent
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import PAYMENT_POLICY
from chatbot.observability.langfuse import link_chatbot_trace
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, log_event
from chatbot.repository.operation_log_repository import collect_payment_context_by_user
from chatbot.schemas import ChatbotState
from common.observability.langfuse import link_current_trace, observe_if_enabled
from common.observability.logger import record_chat_model_usage


PaymentIntentType = Literal["READ_ONLY", "ACTION_REQUEST", "OUT_OF_SCOPE"]


PAYMENT_CLARIFICATION_RESPONSE = (
    "결제/환불 문의 내용을 조금 더 구체적으로 입력해 주세요.\n"
    "예: 결제 상품명, 결제 일시, 주문번호, 결제 플랫폼, 환불 또는 미지급 상황"
)


class PaymentIntentResult(BaseModel):
    intent_type: PaymentIntentType
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal["rule", "llm", "fallback"]
    reason: str = ""


class _PaymentIntentLLMOutput(BaseModel):
    intent_type: PaymentIntentType
    reason: str = ""


READ_ONLY_PATTERNS = (
    r"내역",
    r"상태",
    r"조회",
    r"확인(?:해\s*줘|해주세요|부탁|하고\s*싶|하고싶|할\s*수|되나요|해도|)$",
    r"알려\s*줘",
    r"알고\s*싶",
    r"기록",
    r"로그",
    r"결과",
    r"천장",
    r"어떻게\s*처리",
    r"진행\s*상황",
)

ACTION_PATTERNS = (
    r"환불(?:해\s*줘|해주세요|처리|신청|진행)",
    r"결제\s*취소",
    r"취소(?:해\s*줘|해주세요|처리)",
    r"지급(?:해\s*줘|해주세요|처리|해\s*주세요)",
    r"재지급",
    r"넣어\s*줘",
    r"넣어주세요",
    r"보상(?:해\s*줘|해주세요|넣어|지급|처리)",
    r"복구(?:해\s*줘|해주세요|처리)",
    r"해결(?:해\s*줘|해주세요|처리)",
    r"조치(?:해\s*줘|해주세요|부탁|처리)",
    r"처리(?:해\s*줘|해주세요|부탁)",
    r"승인(?:해\s*줘|해주세요|처리)",
    r"반려(?:해\s*줘|해주세요|처리)",
)

PAYMENT_DOMAIN_PATTERNS = (
    r"결제",
    r"환불",
    r"취소",
    r"주문",
    r"영수증",
    r"구매",
    r"상품",
    r"금액",
    r"플랫폼",
    r"카드",
    r"아이템",
    r"미지급",
    r"지급",
    r"보상",
    r"우편",
    r"가챠",
    r"뽑기",
    r"재화",
    r"원석",
    r"코인",
    r"패키지",
)


def _normalize_intent_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _matches_intent_patterns(patterns: tuple[str, ...], text: str) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


def _classify_payment_intent_by_rule(text: str) -> PaymentIntentResult | None:
    normalized = _normalize_intent_text(text)
    if not normalized:
        return PaymentIntentResult(
            intent_type="OUT_OF_SCOPE",
            confidence=0.95,
            method="fallback",
            reason="empty query is not a payment inquiry",
        )

    domain_hits = _matches_intent_patterns(PAYMENT_DOMAIN_PATTERNS, normalized)
    if not domain_hits:
        return PaymentIntentResult(
            intent_type="OUT_OF_SCOPE",
            confidence=0.95,
            method="rule",
            reason="no payment/refund/item/gacha domain signal",
        )

    action_hits = _matches_intent_patterns(ACTION_PATTERNS, normalized)
    read_hits = _matches_intent_patterns(READ_ONLY_PATTERNS, normalized)

    if action_hits:
        return PaymentIntentResult(
            intent_type="ACTION_REQUEST",
            confidence=0.9,
            method="rule",
            reason=f"action request pattern matched: {action_hits[0]}",
        )
    if read_hits:
        return PaymentIntentResult(
            intent_type="READ_ONLY",
            confidence=0.88,
            method="rule",
            reason=f"read-only inquiry pattern matched: {read_hits[0]}",
        )
    return None


def _payment_intent_llm_enabled() -> bool:
    value = os.environ.get("PAYMENT_INTENT_LLM_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _classify_payment_intent_by_llm(text: str) -> PaymentIntentResult | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or not _payment_intent_llm_enabled():
        return None

    model = os.environ.get("PAYMENT_INTENT_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    classifier = llm.with_structured_output(_PaymentIntentLLMOutput, include_raw=True)
    raw_result = classifier.invoke(
        [
            {
                "role": "system",
                "content": (
                    "Classify a Korean game customer-support payment inquiry.\n"
                    "Return READ_ONLY when the user only asks to view, check, confirm, or explain "
                    "payment/refund/item-delivery/gacha records, status, history, logs, results, or pity count.\n"
                    "Return ACTION_REQUEST only when the user asks the operator or system to perform "
                    "a change or handling action such as refund, cancel, grant, redeliver, recover, compensate, fix, or resolve.\n"
                    "Return OUT_OF_SCOPE when the message is random text, empty, test input, or not about payment, refund, "
                    "item delivery, reward, or gacha.\n"
                    "If the message is a status inquiry even with words like 처리 상태 or 어떻게 처리됐는지, classify READ_ONLY."
                ),
            },
            {"role": "user", "content": text},
        ]
    )
    record_chat_model_usage("payment_intent_classifier", model, raw_result.get("raw"))
    result = raw_result.get("parsed")
    if result is None:
        return None
    return PaymentIntentResult(
        intent_type=result.intent_type,
        confidence=0.8,
        method="llm",
        reason=result.reason,
    )


def classify_payment_intent(text: str) -> dict[str, object]:
    rule_result = _classify_payment_intent_by_rule(text)
    if rule_result is not None:
        return dict(rule_result)

    try:
        llm_result = _classify_payment_intent_by_llm(text)
    except Exception as exc:
        llm_result = PaymentIntentResult(
            intent_type="READ_ONLY",
            confidence=0.55,
            method="fallback",
            reason=f"LLM intent classifier failed; defaulted to read-only: {exc.__class__.__name__}",
        )
    if llm_result is not None:
        return dict(llm_result)

    return PaymentIntentResult(
        intent_type="OUT_OF_SCOPE",
        confidence=0.55,
        method="fallback",
        reason="no high-confidence payment inquiry signal and LLM fallback unavailable",
    ).dict()


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


def _payment_context_message(context: dict[str, Any], payment_intent: dict[str, Any]) -> dict[str, str]:
    # payment agent가 사용자 범위 DB 근거만 보고 답하도록 system message에 DB context를 붙인다.
    return {
        "role": "system",
        "content": (
            "Payment DB context scoped to the logged-in user_id only. "
            "Use this evidence before answering payment/refund/item delivery/gacha questions. "
            "Do not use user-provided account_id or payment_id unless it appears in this context.\n\n"
            "Payment intent classification:\n"
            f"{json.dumps(payment_intent, ensure_ascii=False, default=str)}\n\n"
            "Intent handling rules:\n"
            "- If intent_type is READ_ONLY, provide an AUTO_RESPONSE using the DB evidence. "
            "Do not escalate to operator review only because adjacent records are missing; "
            "state what is confirmed and what is not confirmed.\n"
            "- If intent_type is ACTION_REQUEST, explain that the requested handling requires "
            "operator review or processing. Do not claim that refund, cancellation, compensation, "
            "recovery, or item delivery was already applied.\n\n"
            "Payment context:\n"
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


@observe_if_enabled(
    name="collect_payment_context",
    as_type="tool",
    tags=["chatbot", "feature:payment", "feature:retrieval", "db"],
)
def _collect_payment_context(state: ChatbotState) -> dict[str, Any]:
    # 로그인된 user_id/account_id 기준으로 결제 관련 DB context를 한 번에 조회한다.
    link_current_trace(
        user_id=state.get("user_id"),
        session_id=state.get("session_id"),
        tags=["chatbot", "feature:payment", "feature:retrieval"],
        input_payload=_summarize_payment_context_inputs({"state": state}),
    )
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
    result = collect_payment_context_by_user(
        user_id=int(user_id),
        account_id=state.get("account_id"),
        query_text=_query_text_for_matching(state),
    )
    link_current_trace(
        user_id=state.get("user_id"),
        session_id=state.get("session_id"),
        tags=["chatbot", "feature:payment", "feature:retrieval"],
        output_payload=_summarize_payment_context_outputs(result),
    )
    return result


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
    query_text = _query_text_for_matching(state)
    payment_intent = classify_payment_intent(query_text)
    if payment_intent.get("intent_type") == "OUT_OF_SCOPE":
        update = {
            "draft_text": PAYMENT_CLARIFICATION_RESPONSE,
            "retry_count": state["retry_count"],
            "category": state["category"],
            "routing_target": state["routing_target"],
            "reasoning_node": PAYMENT_POLICY.name,
            "payment_intent": payment_intent,
            "payment_intent_type": payment_intent.get("intent_type"),
            "retrieved_documents": [],
        }
        log_event(
            EVENT_NODE_COMPLETED,
            ticket_id=state.get("ticket_id"),
            session_id=state.get("session_id"),
            node_name=PAYMENT_POLICY.name,
            category=state.get("category"),
            routing_target=state.get("routing_target"),
            metadata={
                "draft_length": len(update["draft_text"]),
                "payment_context_count": 0,
                "payment_evidence_count": 0,
                "payment_intent_type": payment_intent.get("intent_type"),
                "payment_intent_method": payment_intent.get("method"),
            },
        )
        return update

    payment_context = _annotate_item_delivery_relevance(_collect_payment_context(state), state)
    payment_evidence = _payment_context_to_evidence(payment_context)

    # 2단계: DB context를 message와 retrieved_documents에 추가해 agent와 safety가 같은 근거를 보게 한다.
    agent_state = dict(state)
    agent_state["payment_context"] = payment_context
    agent_state["payment_intent"] = payment_intent
    agent_state["payment_intent_type"] = payment_intent.get("intent_type")
    agent_state["retrieved_documents"] = payment_evidence
    messages = [
        *list(state.get("messages") or []),
        _payment_context_message(payment_context, payment_intent),
    ]
    agent_state["messages"] = messages
    result = invoke_payment_agent(agent_state)
    update = build_draft_update(state, result, PAYMENT_POLICY.name)
    update["payment_context"] = payment_context
    update["payment_intent"] = payment_intent
    update["payment_intent_type"] = payment_intent.get("intent_type")
    update["retrieved_documents"] = payment_evidence
    update["review_required"] = payment_intent.get("intent_type") == "ACTION_REQUEST"

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
            "payment_intent_type": payment_intent.get("intent_type"),
            "payment_intent_method": payment_intent.get("method"),
        },
    )
    return update


_original_payment_agent_node = payment_agent_node


@observe_if_enabled(
    name="payment_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "payment"],
)
def payment_agent_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "payment"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "query": state.get("normalized_query") or state.get("raw_query"),
            "routing_target": state.get("routing_target"),
            "account_id": state.get("account_id"),
        },
    )
    result = _original_payment_agent_node(state)
    link_chatbot_trace(
        state,
        tags=["feature:generation", "payment"],
        metadata_source={**state, **result},
        output_payload=result,
    )
    return result
