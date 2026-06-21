from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from chatbot.agent import invoke_bug_agent
from chatbot.generation.faq_agent import _embed_query, _generate_evidence_answer, _rerank_documents
from chatbot.generation.drafting_agent import build_draft_update
from chatbot.generation.policies import BUG_POLICY
from chatbot.observability.langfuse import link_chatbot_trace
from chatbot.observability.logger import EVENT_NODE_COMPLETED, EVENT_NODE_STARTED, EVENT_TOOL_COMPLETED, log_event
from chatbot.schemas import ChatbotState
from common.observability.langfuse import observe_if_enabled
from common.observability.logger import record_chat_model_usage
from common.retrieval.vector_tools import RetrievalQuery, search_document_chunks


BugIntentType = Literal["BUG_REPORT", "NOT_BUG"]


class BugIntentResult(BaseModel):
    intent_type: BugIntentType
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal["rule", "llm", "fallback"]
    reason: str = ""


class _BugIntentLLMOutput(BaseModel):
    intent_type: BugIntentType
    reason: str = ""


BUG_OFF_TOPIC_RESPONSE = (
    "죄송합니다. 이 채널은 버그/오류 문의 전용입니다. "
    "다른 문의는 올바른 카테고리를 선택해 주세요."
)

BUG_REPORT_PATTERNS = (
    r"버그|오류|에러|error|bug|crash|크래시",
    r"튕|꺼지|종료|멈추|멈춤|먹통|프리징|로딩",
    r"안\s*(열|되|떠|보|나오|들어가|넘어가|움직|눌|켜)",
    r"열리지|되지\s*않|안\s*됩니다|안\s*돼|못\s*(받|하|들어가|열|넘어가)",
    r"완료\s*처리|처리\s*안|진행\s*안|다음\s*단계",
    r"두\s*번|중복|반복|계속\s*(돌|나오|뜨|발생)",
    r"카메라|컨트롤러|입력|채팅|링크|초대|보스|임무|퀘스트|그래픽|사운드",
    r"미지급|지급\s*안|우편.*안|보상.*안|가챠|뽑기|기록.*이상",
)

NOT_BUG_PATTERNS = (
    r"환불\s*(처리|승인|취소|요청|해줘|해주세요)",
    r"결제\s*(취소|환불|처리|수단|방법)",
    r"비밀번호|계정\s*(복구|연동|탈퇴|찾기)|로그인\s*방법",
    r"공지|이벤트\s*(기간|보상|참여\s*방법)|업데이트\s*내용",
    r"건의|제안|불만|개선|의견",
)


BUG_REPRODUCTION_FORM_RESPONSE = """문제 확인을 위해 아래 항목을 작성해 주세요.

발생 시점:
오류 메시지:
사용 기기/OS:
오류 내용:"""

BUG_ACCEPTED_RESPONSE = """제공해주신 내용 기준으로 오류 문의가 접수 완료되었습니다.

접수 상태:
접수 완료

저장 내용:
초기 문의와 작성해주신 재현 정보가 문의 내역에 함께 저장되었습니다.

검토 안내:
이후 로그 및 재현 조건 검토가 진행됩니다."""


def _active_query(state: ChatbotState) -> str:
    return str(state.get("normalized_query") or state.get("raw_query") or "").strip()


def _normalize_intent_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _matches_intent_patterns(patterns: tuple[str, ...], text: str) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def _classify_bug_intent_by_rule(text: str) -> BugIntentResult | None:
    normalized = _normalize_intent_text(text)
    if not normalized:
        return BugIntentResult(
            intent_type="NOT_BUG",
            confidence=0.75,
            method="fallback",
            reason="empty query is not a bug report",
        )

    bug_hits = _matches_intent_patterns(BUG_REPORT_PATTERNS, normalized)
    not_bug_hits = _matches_intent_patterns(NOT_BUG_PATTERNS, normalized)

    if bug_hits:
        return BugIntentResult(
            intent_type="BUG_REPORT",
            confidence=0.9,
            method="rule",
            reason=f"bug symptom pattern matched: {bug_hits[0]}",
        )
    if not_bug_hits:
        return BugIntentResult(
            intent_type="NOT_BUG",
            confidence=0.86,
            method="rule",
            reason=f"non-bug support pattern matched: {not_bug_hits[0]}",
        )
    return None


def _bug_intent_llm_enabled() -> bool:
    value = os.environ.get("BUG_INTENT_LLM_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _classify_bug_intent_by_llm(text: str) -> BugIntentResult | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or not _bug_intent_llm_enabled():
        return None

    model = os.environ.get("BUG_INTENT_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    classifier = llm.with_structured_output(_BugIntentLLMOutput, include_raw=True)
    raw_result = classifier.invoke(
        [
            {
                "role": "system",
                "content": (
                    "Classify a Korean game customer-support message for the bug/error agent.\n"
                    "Return BUG_REPORT when the user reports something broken, not opening, not completing, "
                    "duplicated, stuck, crashing, visually/sound/control/input abnormal, or when gacha/item/mail "
                    "records look wrong.\n"
                    "Return NOT_BUG only when the message is clearly about payment/refund/account/FAQ/VOC "
                    "and does not describe malfunctioning game behavior.\n"
                    "When uncertain inside the bug channel, prefer BUG_REPORT."
                ),
            },
            {"role": "user", "content": text},
        ]
    )
    record_chat_model_usage("bug_intent_classifier", model, raw_result.get("raw"))
    result = raw_result.get("parsed")
    if result is None:
        return None
    return BugIntentResult(
        intent_type=result.intent_type,
        confidence=0.8,
        method="llm",
        reason=result.reason,
    )


def classify_bug_intent(text: str) -> dict[str, object]:
    rule_result = _classify_bug_intent_by_rule(text)
    if rule_result is not None:
        return dict(rule_result)

    try:
        llm_result = _classify_bug_intent_by_llm(text)
    except Exception as exc:
        llm_result = BugIntentResult(
            intent_type="BUG_REPORT",
            confidence=0.55,
            method="fallback",
            reason=f"LLM intent classifier failed; defaulted to bug report: {exc.__class__.__name__}",
        )
    if llm_result is not None:
        return dict(llm_result)

    return BugIntentResult(
        intent_type="BUG_REPORT",
        confidence=0.55,
        method="fallback",
        reason="no high-confidence rule hit and LLM fallback unavailable",
    ).dict()


def _state_with_bug_intent(state: ChatbotState, bug_intent: dict[str, object]) -> dict[str, Any]:
    updated = dict(state)
    updated["bug_intent"] = bug_intent
    guidance = (
        "Bug intent precheck: this message is classified as BUG_REPORT. "
        "Do not use the off-topic response unless the user is clearly asking about a non-bug support area."
    )
    messages = list(updated.get("messages") or [])
    if messages:
        messages = [{"role": "system", "content": guidance}, *messages]
    else:
        messages = [{"role": "system", "content": guidance}]
    updated["messages"] = messages
    return updated


def _bug_faq_category() -> str:
    return os.environ.get("BUG_FAQ_CATEGORY", "bug_faq").strip()


def _best_cosine_score(documents: list[dict[str, Any]]) -> float:
    scores = []
    for document in documents:
        try:
            scores.append(float(document.get("cosine_score") or 0))
        except (TypeError, ValueError):
            scores.append(0.0)
    return max(scores or [0.0])


def _best_bm25_score(documents: list[dict[str, Any]]) -> float:
    scores = []
    for document in documents:
        try:
            scores.append(float(document.get("bm25_score") or 0))
        except (TypeError, ValueError):
            scores.append(0.0)
    return max(scores or [0.0])


def _log_bug_faq_precheck(state: ChatbotState, *, status: str, metadata: dict[str, Any]) -> None:
    log_event(
        EVENT_TOOL_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        tool_name="bug_faq_precheck",
        status=status,
        metadata=metadata,
    )


def _run_bug_faq_precheck(state: ChatbotState) -> dict[str, Any] | None:
    if state.get("bug_collection_status") != "collecting":
        return None

    bug_faq_category = _bug_faq_category()
    query = _active_query(state)
    if not bug_faq_category or not query:
        _log_bug_faq_precheck(
            state,
            status="skipped",
            metadata={"reason": "missing_category_or_query", "bug_faq_category": bug_faq_category, "query": query},
        )
        return None

    try:
        embedding_json = _embed_query(query)
        candidate_top_k = int(os.environ.get("BUG_FAQ_CANDIDATE_TOP_K", "8"))
        final_top_k = int(os.environ.get("BUG_FAQ_TOP_K", "3"))
        documents = search_document_chunks(
            embedding_json=embedding_json,
            query_text=query,
            top_k=candidate_top_k,
            prefer_faq=False,
            enrichment=RetrievalQuery(
                query_text=query,
                preferred_source_types=[],
                preferred_categories=[bug_faq_category],
            ),
        )
        documents = _rerank_documents(documents, query)[:final_top_k]
        documents = [doc for doc in documents if str(doc.get("category") or "") == bug_faq_category]
        best_cosine = _best_cosine_score(documents)
        best_bm25 = _best_bm25_score(documents)
    except Exception as exc:
        _log_bug_faq_precheck(
            state,
            status="error",
            metadata={
                "reason": "retrieval_failed",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return None

    if not documents:
        _log_bug_faq_precheck(
            state,
            status="skipped",
            metadata={
                "reason": "no_bug_faq_document",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "document_count": len(documents),
                "best_cosine_score": best_cosine,
                "best_bm25_score": best_bm25,
                "top_documents": [
                    {
                        "document_id": doc.get("document_id"),
                        "chunk_id": doc.get("chunk_id"),
                        "category": doc.get("category"),
                        "title": doc.get("title"),
                        "cosine_score": doc.get("cosine_score"),
                        "score": doc.get("score"),
                    }
                    for doc in documents[:3]
                ],
            },
        )
        return None

    try:
        answer = _generate_evidence_answer(
            original_query=query,
            retrieval_query=query,
            documents=documents,
        )
    except Exception as exc:
        _log_bug_faq_precheck(
            state,
            status="error",
            metadata={
                "reason": "answer_generation_failed",
                "bug_faq_category": bug_faq_category,
                "query": query,
                "document_count": len(documents),
                "best_cosine_score": best_cosine,
                "best_bm25_score": best_bm25,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return None
    _log_bug_faq_precheck(
        state,
        status="ok",
        metadata={
            "reason": "matched",
            "bug_faq_category": bug_faq_category,
            "query": query,
            "document_count": len(documents),
            "best_cosine_score": best_cosine,
            "best_bm25_score": best_bm25,
        },
    )
    return {
        "draft_text": answer,
        "retry_count": state["retry_count"],
        "category": state["category"],
        "routing_target": state["routing_target"],
        "reasoning_node": BUG_POLICY.name,
        "bug_collection_status": None,
        "retrieved_documents": documents,
        "retrieved_count": len(documents),
        "retrieval_query": query,
        "retrieval_enrichment": {
            "bug_faq_category": bug_faq_category,
            "best_cosine_score": best_cosine,
            "best_bm25_score": best_bm25,
        },
        "faq_failure_reason": None,
    }


def bug_agent_node(state: ChatbotState) -> dict:
    # 1단계: 버그 문의는 자동 확정 답변보다 재현 정보 수집/검토 안내 중심으로 초안을 만든다.
    log_event(
        EVENT_NODE_STARTED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
    )
    bug_intent = (
        {"intent_type": "BUG_REPORT", "confidence": 1.0, "method": "conversation", "reason": "active bug collection"}
        if state.get("bug_collection_status")
        else classify_bug_intent(_active_query(state))
    )

    if bug_intent.get("intent_type") == "NOT_BUG":
        update = {
            "draft_text": BUG_OFF_TOPIC_RESPONSE,
            "retry_count": state["retry_count"],
            "category": state["category"],
            "routing_target": state["routing_target"],
            "reasoning_node": BUG_POLICY.name,
            "bug_intent": bug_intent,
            "safety_action": "AUTO_RESPONSE",
            "safety_passed": True,
            "review_required": False,
        }
    else:
        bug_faq_update = _run_bug_faq_precheck(state)
        if bug_faq_update is not None:
            update = {**bug_faq_update, "bug_intent": bug_intent, "review_required": False}
        elif state.get("bug_collection_status") == "collecting":
            update = {
                "draft_text": BUG_REPRODUCTION_FORM_RESPONSE,
                "retry_count": state["retry_count"],
                "category": state["category"],
                "routing_target": state["routing_target"],
                "reasoning_node": BUG_POLICY.name,
                "bug_intent": bug_intent,
                "safety_action": "AUTO_RESPONSE",
                "safety_passed": True,
                "review_required": False,
            }
        elif state.get("bug_collection_status") == "ready_for_review":
            update = {
                "draft_text": BUG_ACCEPTED_RESPONSE,
                "retry_count": state["retry_count"],
                "category": state["category"],
                "routing_target": state["routing_target"],
                "reasoning_node": BUG_POLICY.name,
                "bug_intent": bug_intent,
                "safety_action": "REVIEW_REQUIRED",
                "safety_passed": True,
                "review_required": True,
            }
        else:
            result = invoke_bug_agent(_state_with_bug_intent(state, bug_intent))
            update = {
                **build_draft_update(state, result, BUG_POLICY.name),
                "bug_intent": bug_intent,
                "review_required": True,
            }

    # 2단계: 생성된 버그 초안 길이를 기록하고 공통 draft_persistence 노드로 넘긴다.
    log_event(
        EVENT_NODE_COMPLETED,
        ticket_id=state.get("ticket_id"),
        session_id=state.get("session_id"),
        node_name=BUG_POLICY.name,
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        metadata={"draft_length": len(update.get("draft_text") or "")},
    )
    return update


_original_run_bug_faq_precheck = _run_bug_faq_precheck


@observe_if_enabled(
    name="bug_faq_precheck",
    as_type="tool",
    tags=["chatbot", "feature:retrieval", "bug", "faq_precheck"],
)
def _run_bug_faq_precheck(state: ChatbotState) -> dict[str, Any] | None:
    link_chatbot_trace(
        state,
        tags=["feature:retrieval", "bug", "faq_precheck"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "query": state.get("normalized_query") or state.get("raw_query"),
            "bug_collection_status": state.get("bug_collection_status"),
        },
    )
    result = _original_run_bug_faq_precheck(state)
    link_chatbot_trace(
        state,
        tags=["feature:retrieval", "bug", "faq_precheck"],
        metadata_source={**state, **(result or {})},
        output_payload=result or {"matched": False},
    )
    return result


_original_bug_agent_node = bug_agent_node


@observe_if_enabled(
    name="bug_agent",
    as_type="chain",
    tags=["chatbot", "feature:generation", "bug"],
)
def bug_agent_node(state: ChatbotState) -> dict:
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        input_payload={
            "ticket_id": state.get("ticket_id"),
            "query": state.get("normalized_query") or state.get("raw_query"),
            "routing_target": state.get("routing_target"),
            "bug_collection_status": state.get("bug_collection_status"),
        },
    )
    result = _original_bug_agent_node(state)
    link_chatbot_trace(
        state,
        tags=["feature:generation", "bug"],
        metadata_source={**state, **result},
        output_payload=result,
    )
    return result
