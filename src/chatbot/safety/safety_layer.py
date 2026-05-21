from __future__ import annotations

import os

from chatbot.observability.logger import EVENT_SAFETY_CHECKED, log_event
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results


MODERATION_MODEL = "omni-moderation-latest"


def _as_dict(value: object) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


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
            "factuality_score": 0.8,
            "hallucination_score": 0.2,
        },
        (
            f"moderation model={MODERATION_MODEL}; "
            f"flagged_categories={flagged_categories or ['none']}"
        ),
    )


def _evaluate_safety(text: str) -> tuple[bool, dict[str, float], str]:
    return _moderation_safety_check(text)


def safety_layer_node(state: ChatbotState) -> dict:
    draft_text = state["draft_text"]
    draft_id = state["draft_id"]
    ticket_id = state["ticket_id"]
    is_blocked, scores, safety_reason = _evaluate_safety(draft_text)
    safety_passed = not is_blocked
    safety_action = "AUTO_RESPONSE" if safety_passed else "BLOCK_RESPONSE"

    write_safety_results.invoke({
        "payload": {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "safety_action": safety_action,
            "factuality_score": scores["factuality_score"],
            "hallucination_score": scores["hallucination_score"],
            "toxicity_score": scores["toxicity_score"],
            "policy_violation_score": scores["policy_violation_score"],
            "safety_reason": safety_reason,
            "review_required": False,
            "retry_count": state["retry_count"] + (1 if is_blocked else 0),
        },
    })

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
        },
    )

    return {
        "safety_passed": safety_passed,
        "safety_action": safety_action,
        "safety_reason": safety_reason,
        "review_required": safety_action == "REVIEW_QUEUE",
        "retry_count": state["retry_count"] + (1 if is_blocked else 0),
    }
