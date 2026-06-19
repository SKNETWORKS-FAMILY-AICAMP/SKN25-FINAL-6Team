from __future__ import annotations

import json
import os
import re
from typing import Any

from chatbot.constants import (
    FACTUALITY_BLOCK_THRESHOLD,
    FACTUALITY_THRESHOLD,
    FACTUALITY_WARN_THRESHOLD,
    HALLUCINATION_BLOCK_THRESHOLD,
    HALLUCINATION_THRESHOLD,
    HALLUCINATION_WARN_THRESHOLD,
    MAX_MASKING_RETRY,
    TOXICITY_THRESHOLD,
)
from chatbot.generation.response.fixed_responses import SAFE_FALLBACK_RESPONSE
from chatbot.observability.logger import EVENT_SAFETY_CHECKED, log_event
from chatbot.repository.safety_repository import save_safety_results
from chatbot.schemas import ChatbotState
from common.observability.logger import estimate_tokens, record_usage


MODERATION_MODEL = "omni-moderation-latest"

MASK_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[이메일]"),
    ("phone", r"\b01[016789]-?\d{3,4}-?\d{4}\b", "[전화번호]"),
    ("card_number", r"\b(?:\d[ -]?){13,19}\b", "[카드번호]"),
    ("api_key", r"\b(?:sk|rk|pk|sess|token|key)-[A-Za-z0-9_-]{16,}\b", "[인증정보]"),
    ("account_id", r"\b(?:account_id|user_id|uid|회원번호|계정번호)\s*[:=]\s*[A-Za-z0-9_-]{4,}\b", "[계정정보]"),
)


def _as_dict(value: object) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[0-9A-Za-z\uac00-\ud7a3_]+", text)
        if len(token.strip()) > 1
    }


def _evidence_text(documents: list[dict[str, Any]]) -> str:
    parts = []
    for document in documents:
        parts.extend(
            [
                str(document.get("title") or ""),
                str(document.get("category") or ""),
                str(document.get("chunk_text") or ""),
            ]
        )
    return "\n".join(parts)


def _mask_sensitive_text(text: str) -> tuple[str, list[str]]:
    masked = text
    applied: list[str] = []
    for label, pattern, replacement in MASK_PATTERNS:
        masked, count = re.subn(pattern, replacement, masked, flags=re.IGNORECASE)
        if count:
            applied.append(label)
    return masked, applied


MASK_PATTERNS = (
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[이메일]"),
    ("phone", r"\b01[016789]-?\d{3,4}-?\d{4}\b", "[전화번호]"),
    ("url", r"\b(?:https?://|www\.)[^\s<>()\[\]{}\"']+", "[홈페이지]"),
    ("card_number", r"\b(?:\d[ -]?){13,19}\b", "[카드번호]"),
    ("api_key", r"\b(?:sk|rk|pk|sess|token|key)-[A-Za-z0-9_-]{16,}\b", "[인증정보]"),
    ("account_id", r"\b(?:account_id|user_id|uid|회원번호|계정번호)\s*[:=]\s*[A-Za-z0-9_-]{4,}\b", "[계정정보]"),
)
DOCUMENT_GROUNDED_CONTACT_LABELS = {"email", "phone", "url"}


def _normalize_contact_value(label: str, value: str) -> str:
    cleaned = value.strip().strip(".,;:!?)]}>'\"")
    if label == "phone":
        return re.sub(r"\D", "", cleaned)
    return cleaned.lower()


def _document_grounded_contact_values(documents: list[dict[str, Any]]) -> dict[str, set[str]]:
    evidence = _evidence_text(documents)
    grounded = {label: set() for label in DOCUMENT_GROUNDED_CONTACT_LABELS}
    if not evidence.strip():
        return grounded

    for label, pattern, _ in MASK_PATTERNS:
        if label not in DOCUMENT_GROUNDED_CONTACT_LABELS:
            continue
        for match in re.finditer(pattern, evidence, flags=re.IGNORECASE):
            grounded[label].add(_normalize_contact_value(label, match.group(0)))
    return grounded


def _is_document_grounded_contact(
    *,
    label: str,
    value: str,
    grounded_contacts: dict[str, set[str]],
) -> bool:
    if label not in DOCUMENT_GROUNDED_CONTACT_LABELS:
        return False
    return _normalize_contact_value(label, value) in grounded_contacts.get(label, set())


def _mask_sensitive_text(
    text: str,
    documents: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    masked = text
    applied: list[str] = []
    grounded_contacts = _document_grounded_contact_values(documents or [])

    for label, pattern, replacement in MASK_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if _is_document_grounded_contact(
                label=label,
                value=value,
                grounded_contacts=grounded_contacts,
            ):
                return value
            if label not in applied:
                applied.append(label)
            return replacement

        masked = re.sub(pattern, replace, masked, flags=re.IGNORECASE)
    return masked, applied


def _evidence_grounding_scores(text: str, documents: list[dict[str, Any]]) -> tuple[float, float, str]:
    # 런타임 경량 검사: 답변 토큰이 검색/DB 근거에 얼마나 포함되는지로 grounding을 추정한다.
    normalized_text = " ".join(text.split())
    if not normalized_text:
        return 1.0, 0.0, "empty draft"

    if not documents:
        if normalized_text == SAFE_FALLBACK_RESPONSE:
            return 1.0, 0.0, "fallback response without retrieved evidence"
        return 0.0, 1.0, "no retrieved evidence for generated draft"

    answer_tokens = _tokenize(normalized_text)
    evidence_tokens = _tokenize(_evidence_text(documents))
    if not answer_tokens:
        return 1.0, 0.0, "draft has no comparable tokens"
    if not evidence_tokens:
        return 0.0, 1.0, "retrieved evidence has no comparable tokens"

    covered = answer_tokens & evidence_tokens
    factuality_score = len(covered) / len(answer_tokens)
    hallucination_score = 1.0 - factuality_score
    return (
        round(factuality_score, 4),
        round(hallucination_score, 4),
        f"evidence token coverage={len(covered)}/{len(answer_tokens)}",
    )


def _moderation_safety_check(text: str) -> tuple[bool, dict[str, float], str]:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI API key is missing.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.moderations.create(
        model=MODERATION_MODEL,
        input=text,
    )
    record_usage(
        component="safety_moderation",
        model=MODERATION_MODEL,
        prompt_tokens=estimate_tokens(text, MODERATION_MODEL),
        completion_tokens=0,
        successful_requests=1,
        estimated=True,
    )
    result = response.results[0]
    scores = _as_dict(result.category_scores)
    categories = _as_dict(result.categories)

    toxicity_score = max(
        float(scores.get(name, 0.0))
        for name in (
            "harassment",
            "harassment/threatening",
            "hate",
            "hate/threatening",
            "violence",
            "violence/graphic",
        )
    )
    policy_violation_score = max([float(score) for score in scores.values()] or [0.0])
    flagged_categories = [
        name for name, flagged in categories.items()
        if flagged
    ]

    return (
        bool(result.flagged),
        {
            "toxicity_score": toxicity_score,
            "policy_violation_score": policy_violation_score,
        },
        (
            f"moderation model={MODERATION_MODEL}; "
            f"flagged_categories={flagged_categories or ['none']}"
        ),
    )


def _evaluate_safety(text: str, documents: list[dict[str, Any]] | None = None) -> tuple[bool, dict[str, float], str]:
    is_blocked, scores, moderation_reason = _moderation_safety_check(text)
    factuality_score, hallucination_score, grounding_reason = _evidence_grounding_scores(
        text,
        documents or [],
    )
    scores.update(
        {
            "factuality_score": factuality_score,
            "hallucination_score": hallucination_score,
        }
    )
    return is_blocked, scores, f"{moderation_reason}; grounding={grounding_reason}"


def _lightweight_safety_scores(text: str, documents: list[dict[str, Any]]) -> tuple[dict[str, float], str]:
    factuality_score, hallucination_score, grounding_reason = _evidence_grounding_scores(
        text,
        documents,
    )
    return (
        {
            "toxicity_score": 0.0,
            "policy_violation_score": 0.0,
            "factuality_score": factuality_score,
            "hallucination_score": hallucination_score,
        },
        f"rule_base: moderation skipped; grounding={grounding_reason}",
    )


def _contains_sensitive_keyword(text: str) -> bool:
    return bool(
        re.search(
            r"결제|환불|취소|계정\s*복구|계정\s*삭제|탈퇴|비밀번호|토큰|카드|개인정보|주민번호|관리자|운영자",
            text,
            flags=re.IGNORECASE,
        )
    )


def _requires_second_pass_safety(
    *,
    state: ChatbotState,
    evaluation_text: str,
    documents: list[dict[str, Any]],
    requires_grounding: bool,
    scores: dict[str, float],
    mask_labels: list[str],
) -> tuple[bool, str]:
    # 1차 rule 검사에서 민감/불확실 신호가 있으면 2차 moderation/grounding 검사를 수행한다.
    detected_labels = set(state.get("input_detected_labels") or [])
    sensitive_labels = {
        "rrn",
        "card_number",
        "email",
        "phone",
        "api_key",
        "password",
        "account_id",
        "prompt_injection",
        "profanity",
    }
    if mask_labels or detected_labels & sensitive_labels:
        return True, "sensitive_or_masked_content"

    if str(state.get("category") or "").lower() == "payment":
        return True, "payment_sensitive_category"

    if _contains_sensitive_keyword(
        " ".join(
            str(state.get(key) or "")
            for key in ("raw_query", "masked_content", "normalized_query", "draft_text")
        )
    ):
        return True, "sensitive_keyword"

    if state.get("review_required") is True:
        return True, "review_candidate"

    if not evaluation_text.strip() or len(evaluation_text.strip()) < 10:
        return True, "short_or_empty_draft"

    if requires_grounding:
        if not documents:
            return True, "missing_grounding_documents"
        if (
            scores["factuality_score"] < FACTUALITY_WARN_THRESHOLD
            or scores["hallucination_score"] > HALLUCINATION_WARN_THRESHOLD
        ):
            return True, "weak_grounding"

    return False, "simple_rule_pass"


def _requires_document_grounding(state: ChatbotState, documents: list[dict[str, Any]]) -> bool:
    routing_target = str(state.get("routing_target") or "").strip().lower()
    return (
        state.get("reasoning_node") == "faq_agent"
        or str(state.get("category") or "").lower() == "faq"
        or routing_target in {"faq_agent", "rag_reply"}
    )


def _status_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_any_status(rows: list[dict[str, Any]], field: str, statuses: set[str]) -> bool:
    return any(_status_text(row.get(field)) in statuses for row in rows)


def _payment_context_requires_review(state: ChatbotState) -> tuple[bool, str | None]:
    context = state.get("payment_context")
    if not isinstance(context, dict):
        return False, None

    if state.get("payment_intent_type") == "READ_ONLY":
        return False, None

    if state.get("payment_intent_type") == "ACTION_REQUEST":
        return True, "payment_action_request_requires_operator_review"

    data = context.get("data")
    if not isinstance(data, dict):
        return False, None

    refunds = data.get("refunds") if isinstance(data.get("refunds"), list) else []
    deliveries = data.get("item_delivery_logs") if isinstance(data.get("item_delivery_logs"), list) else []
    payments = data.get("payments") if isinstance(data.get("payments"), list) else []
    user_text = " ".join(
        str(state.get(key) or "")
        for key in ("raw_query", "masked_content", "normalized_query", "sub_category")
    )

    if _has_any_status(refunds, "refund_status", {"requested", "pending", "reviewing", "in_progress", "processing"}):
        return True, "refund_status_requires_operator_review"

    asks_delivery_or_reward = bool(re.search(r"지급|미지급|아이템|보상|언제|안\s*들어|못\s*받|반영", user_text))
    has_completed_payment = _has_any_status(
        payments,
        "payment_status",
        {"completed", "complete", "success", "succeeded", "paid", "완료", "성공"},
    )
    has_delivered_item = _has_any_status(
        deliveries,
        "delivery_status",
        {"delivered", "completed", "complete", "success", "완료", "지급완료"},
    )
    has_pending_or_failed_delivery = _has_any_status(
        deliveries,
        "delivery_status",
        {"pending", "failed", "processing", "requested", "미지급", "대기", "실패"},
    )
    if asks_delivery_or_reward and has_completed_payment and (has_pending_or_failed_delivery or not has_delivered_item):
        return True, "paid_item_delivery_requires_operator_review"

    return False, None


def _operator_review_signal(state: ChatbotState, draft_text: str) -> tuple[bool, str | None]:
    if state.get("review_required") is True:
        return True, "review_already_requested"

    context_required, context_reason = _payment_context_requires_review(state)
    if context_required:
        return True, context_reason

    combined_text = " ".join(
        str(value or "")
        for value in (
            state.get("raw_query"),
            state.get("masked_content"),
            state.get("normalized_query"),
            state.get("sub_category"),
            draft_text,
        )
    )
    strong_review_patterns = (
        r"담당자.{0,12}(확인|검토|처리|안내)",
        r"운영자.{0,12}(확인|검토|처리|안내)",
        r"티켓.{0,12}(검토|접수|처리)",
        r"(문의|오류|버그).{0,12}접수",
        r"접수.{0,12}(되었|됐|완료)",
        r"별도.{0,8}안내",
        r"(수동|직접).{0,8}(지급|보상|환불|복구|처리)",
        r"(환불|결제\s*취소).{0,12}(승인|처리|검토|진행\s*중)",
        r"(계정\s*복구|제재\s*해제|연동\s*해제).{0,12}(필요|요청|검토|처리)",
        r"(로그|재현|증빙|영수증).{0,12}(확인|검토).{0,12}(필요|대상)",
        r"(로그|재현).{0,12}(검토|확인).{0,12}(필요|진행|대상)",
        r"(자동|AI).{0,8}(처리|확답|판단).{0,8}(어렵|불가)",
    )
    for pattern in strong_review_patterns:
        if re.search(pattern, combined_text, flags=re.IGNORECASE):
            return True, f"operator_review_signal:{pattern}"

    return False, None


def _decide_safety_action(
    *,
    moderation_blocked: bool,
    scores: dict[str, float],
    draft_text: str,
    documents: list[dict[str, Any]],
    state: ChatbotState,
    requires_grounding: bool = True,
) -> tuple[bool, str, bool]:
    # safety 점수와 grounding 결과를 AUTO_RESPONSE/SAFE_FALLBACK/BLOCK/REVIEW_REQUIRED로 변환한다.
    if moderation_blocked or scores["toxicity_score"] >= TOXICITY_THRESHOLD:
        return False, "BLOCK_RESPONSE", False

    if "policy_violation_score" in scores and scores["policy_violation_score"] >= TOXICITY_THRESHOLD:
        return False, "BLOCK_RESPONSE", False

    operator_review_required, _ = _operator_review_signal(state, draft_text)
    if operator_review_required:
        return True, "REVIEW_REQUIRED", True

    normalized_text = " ".join(draft_text.split())
    if not requires_grounding:
        return True, "AUTO_RESPONSE", False

    grounding_failed = (
        scores["factuality_score"] < FACTUALITY_THRESHOLD
        or scores["hallucination_score"] > HALLUCINATION_THRESHOLD
    )
    if not grounding_failed:
        return True, "AUTO_RESPONSE", False

    if normalized_text == SAFE_FALLBACK_RESPONSE:
        return True, "AUTO_RESPONSE", False

    if not documents:
        return False, "SAFE_FALLBACK", False

    severely_ungrounded = (
        scores["factuality_score"] < FACTUALITY_BLOCK_THRESHOLD
        or scores["hallucination_score"] > HALLUCINATION_BLOCK_THRESHOLD
    )
    if severely_ungrounded:
        return False, "SAFE_FALLBACK", False

    weak_grounding = (
        scores["factuality_score"] < FACTUALITY_WARN_THRESHOLD
        or scores["hallucination_score"] > HALLUCINATION_WARN_THRESHOLD
    )
    return True, "AUTO_RESPONSE", weak_grounding


def _masking_update(
    *,
    state: ChatbotState,
    scores: dict[str, float],
    safety_reason: str,
    masked_text: str,
    mask_labels: list[str],
) -> dict[str, Any]:
    retry_count = state["retry_count"] + 1
    retry_exhausted = retry_count > MAX_MASKING_RETRY
    safety_action = "SAFE_FALLBACK" if retry_exhausted else "MASKING"
    review_required = False
    next_draft_text = SAFE_FALLBACK_RESPONSE if retry_exhausted else masked_text
    reason = (
        f"{safety_reason}; masking_applied={mask_labels}; "
        f"masking_retry={retry_count}/{MAX_MASKING_RETRY}"
    )
    if retry_exhausted:
        reason = f"{reason}; masking retry exhausted"

    safety_result = _write_safety_results(
        {
            "draft_id": state.get("draft_id"),
            "ticket_id": state["ticket_id"],
            "safety_action": safety_action,
            "factuality_score": scores["factuality_score"],
            "hallucination_score": scores["hallucination_score"],
            "toxicity_score": scores["toxicity_score"],
            "policy_violation_score": scores["policy_violation_score"],
            "safety_reason": reason,
            "review_required": review_required,
            "retry_count": retry_count,
        }
    )

    return {
        "draft_text": next_draft_text,
        "safety_passed": False,
        "safety_action": safety_action,
        "safety_reason": reason,
        "factuality_score": scores["factuality_score"],
        "hallucination_score": scores["hallucination_score"],
        "toxicity_score": scores["toxicity_score"],
        "policy_violation_score": scores["policy_violation_score"],
        "review_required": review_required,
        "masking_applied": bool(mask_labels),
        "masking_labels": mask_labels,
        "retry_count": retry_count,
        "safety_result": safety_result,
    }


def _write_safety_results(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("draft_id") is None:
        return {
            "status": "skipped",
            "stored": False,
            "reason": "missing_draft_id",
            "payload": payload,
        }
    return save_safety_results(payload)


def safety_layer_node(state: ChatbotState) -> dict:
    # 1단계: 초안에서 민감정보를 마스킹하고, FAQ/RAG 답변이면 근거 문서를 함께 검사한다.
    draft_text = state["draft_text"]
    draft_id = state.get("draft_id")
    ticket_id = state["ticket_id"]
    documents = state.get("retrieved_documents") or []
    masked_text, mask_labels = _mask_sensitive_text(draft_text, documents)
    evaluation_text = masked_text if mask_labels else draft_text
    requires_grounding = _requires_document_grounding(state, documents)
    grounding_documents = documents if requires_grounding else [{"chunk_text": evaluation_text}]
    scores, safety_reason = _lightweight_safety_scores(evaluation_text, grounding_documents)
    second_pass_required, second_pass_reason = _requires_second_pass_safety(
        state=state,
        evaluation_text=evaluation_text,
        documents=documents,
        requires_grounding=requires_grounding,
        scores=scores,
        mask_labels=mask_labels,
    )
    is_blocked = False
    if second_pass_required:
        # 2단계: 민감 문의나 약한 grounding은 OpenAI moderation까지 포함한 2차 검사를 수행한다.
        is_blocked, scores, safety_reason = _evaluate_safety(evaluation_text, grounding_documents)
        safety_reason = f"{safety_reason}; second_pass={second_pass_reason}"
    else:
        safety_reason = f"{safety_reason}; second_pass={second_pass_reason}"
    if mask_labels:
        # 3단계-A: 답변에 개인정보가 남아 있으면 마스킹된 초안으로 재저장하도록 라우팅한다.
        update = _masking_update(
            state=state,
            scores=scores,
            safety_reason=safety_reason,
            masked_text=masked_text,
            mask_labels=mask_labels,
        )
        log_event(
            EVENT_SAFETY_CHECKED,
            ticket_id=ticket_id,
            session_id=state.get("session_id"),
            node_name="safety_layer",
            category=state.get("category"),
            routing_target=state.get("routing_target"),
            status="ok",
            metadata={
                "safety_passed": update["safety_passed"],
                "safety_action": update["safety_action"],
                "draft_id": draft_id,
                "masking_labels": mask_labels,
            },
        )
        return update

    # 3단계-B: 마스킹이 필요 없으면 safety action을 결정하고 결과를 DB에 저장한다.
    safety_passed, safety_action, review_required = _decide_safety_action(
        moderation_blocked=is_blocked,
        scores=scores,
        draft_text=draft_text,
        documents=documents,
        state=state,
        requires_grounding=requires_grounding,
    )
    operator_review_required, operator_review_reason = _operator_review_signal(state, draft_text)
    if operator_review_required:
        safety_reason = f"{safety_reason}; review={operator_review_reason}"

    safety_result = _write_safety_results(
        {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "safety_action": safety_action,
            "factuality_score": scores["factuality_score"],
            "hallucination_score": scores["hallucination_score"],
            "toxicity_score": scores["toxicity_score"],
            "policy_violation_score": scores["policy_violation_score"],
            "safety_reason": safety_reason,
            "review_required": review_required,
            "retry_count": state["retry_count"] + (1 if not safety_passed else 0),
        }
    )

    log_event(
        EVENT_SAFETY_CHECKED,
        ticket_id=ticket_id,
        session_id=state.get("session_id"),
        node_name="safety_layer",
        category=state.get("category"),
        routing_target=state.get("routing_target"),
        status="ok",
        metadata={
            "safety_passed": safety_passed,
            "safety_action": safety_action,
            "draft_id": draft_id,
            "review_required": review_required,
            "second_pass_required": second_pass_required,
            "second_pass_reason": second_pass_reason,
        },
    )

    return {
        "safety_passed": safety_passed,
        "safety_action": safety_action,
        "safety_reason": safety_reason,
        "factuality_score": scores["factuality_score"],
        "hallucination_score": scores["hallucination_score"],
        "toxicity_score": scores["toxicity_score"],
        "policy_violation_score": scores["policy_violation_score"],
        "review_required": review_required,
        "retry_count": state["retry_count"] + (1 if not safety_passed else 0),
        "safety_result": safety_result,
    }
