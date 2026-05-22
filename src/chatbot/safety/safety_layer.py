from __future__ import annotations

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
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results


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


def _evidence_grounding_scores(text: str, documents: list[dict[str, Any]]) -> tuple[float, float, str]:
    """Estimate factuality/hallucination from retrieved evidence coverage.

    This is a lightweight runtime checker. RAGAS still remains the deeper offline
    evaluation path for faithfulness and factual correctness.
    """
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


def _requires_document_grounding(state: ChatbotState, documents: list[dict[str, Any]]) -> bool:
    if documents:
        return True
    return state.get("reasoning_node") == "faq_agent" or state.get("category") == "FAQ"


def _decide_safety_action(
    *,
    moderation_blocked: bool,
    scores: dict[str, float],
    draft_text: str,
    documents: list[dict[str, Any]],
    requires_grounding: bool = True,
) -> tuple[bool, str, bool]:
    if moderation_blocked or scores["toxicity_score"] >= TOXICITY_THRESHOLD:
        return False, "BLOCK_RESPONSE", False

    if "policy_violation_score" in scores and scores["policy_violation_score"] >= TOXICITY_THRESHOLD:
        return False, "BLOCK_RESPONSE", False

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

    _write_safety_results(
        {
            "draft_id": state["draft_id"],
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
    }


def _write_safety_results(payload: dict[str, Any]) -> str:
    return write_safety_results.invoke({"payload": payload})


def safety_layer_node(state: ChatbotState) -> dict:
    draft_text = state["draft_text"]
    draft_id = state["draft_id"]
    ticket_id = state["ticket_id"]
    documents = state.get("retrieved_documents") or []
    masked_text, mask_labels = _mask_sensitive_text(draft_text)
    evaluation_text = masked_text if mask_labels else draft_text
    requires_grounding = _requires_document_grounding(state, documents)
    grounding_documents = documents if requires_grounding else [{"chunk_text": evaluation_text}]
    is_blocked, scores, safety_reason = _evaluate_safety(evaluation_text, grounding_documents)
    if mask_labels:
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

    safety_passed, safety_action, review_required = _decide_safety_action(
        moderation_blocked=is_blocked,
        scores=scores,
        draft_text=draft_text,
        documents=documents,
        requires_grounding=requires_grounding,
    )

    _write_safety_results(
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
    }
