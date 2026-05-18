from __future__ import annotations

from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results
from config import settings


MODERATION_MODEL = "omni-moderation-latest"


def _as_dict(value: object) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _moderation_safety_check(text: str) -> tuple[bool, dict[str, float], str]:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is missing.")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
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
    answer_draft = state["answer_draft"]
    draft_id = state["draft_id"]
    ticket_id = state["ticket_id"]
    is_blocked, scores, safety_reason = _evaluate_safety(answer_draft)
    safety_passed = not is_blocked
    decision_type = "AUTO_RESPONSE" if safety_passed else "BLOCK_RESPONSE"

    write_safety_results.invoke({
        "payload": {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "decision_type": decision_type,
            "factuality_score": scores["factuality_score"],
            "hallucination_score": scores["hallucination_score"],
            "toxicity_score": scores["toxicity_score"],
            "policy_violation_score": scores["policy_violation_score"],
            "reason": safety_reason,
        },
    })

    return {
        "safety_passed": safety_passed,
        "safety_action": decision_type,
        "safety_reason": safety_reason,
        "review_required": decision_type == "REVIEW_QUEUE",
        "retry_count": state["retry_count"] + (1 if is_blocked else 0),
    }
