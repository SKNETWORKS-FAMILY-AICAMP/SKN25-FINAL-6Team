from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

ROOT_DIR = Path(__file__).resolve().parents[2]
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from chatbot.constants import (
    FACTUALITY_THRESHOLD,
    FINAL_DECISION_AUTO,
    FINAL_DECISION_BLOCK,
    FINAL_DECISION_FALLBACK,
    FINAL_DECISION_MASKING,
    FINAL_DECISION_REVIEW,
    FIXED_BLOCK_MESSAGE,
    FIXED_FALLBACK_MESSAGE,
    HALLUCINATION_THRESHOLD,
    HARASSMENT_THRESHOLD,
    HATE_THRESHOLD,
    MAX_SAFETY_RETRY,
    TOXICITY_THRESHOLD,
    VIOLENCE_THRESHOLD,
)
from chatbot.schemas import ChatbotState
from chatbot.tools.db_tools import write_safety_results
from config import settings

# ── 프롬프트 ────────────────────────────────────────────────────────────────

_RESPONSE_VALIDATION_PROMPT = f"""CS 답변의 사실성과 환각 여부를 평가하세요.
0.0~1.0 점수로 JSON만 반환하세요.

{{"factuality": 0.0, "hallucination": 0.0}}

- factuality : 실제 데이터·정책에 근거한 정도 (높을수록 좋음)
- hallucination : 근거 없는 정보 포함 정도 (낮을수록 좋음)"""

_MODERATION_PROMPT = f"""CS 답변의 유해성을 평가하세요.
0.0~1.0 점수로 JSON만 반환하세요.

{{"toxicity": 0.0, "hate": 0.0, "violence": 0.0, "harassment": 0.0}}"""

_PII_DETECTION_PROMPT = """CS 답변에 개인정보(주민번호, 전화번호, 이메일, 계좌번호, 주소 등)가 포함되어 있는지 확인하세요.
게임 UID·티켓 ID·상품명은 개인정보가 아닙니다 (allowlist).
JSON만 반환하세요.

{"pii_detected": false, "masked_text": "원문 또는 마스킹된 텍스트"}"""


# ── LLM ─────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def _call(llm: ChatOpenAI, system: str, user: str) -> dict:
    try:
        res = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return json.loads(res.content)
    except (json.JSONDecodeError, AttributeError):
        return {}


# ── final_decision 결정 ───────────────────────────────────────────────────────

def _decide(
    rv: dict,
    mod: dict,
    pii: dict,
    category: str,
    routing_target: str,
    retry_count: int,
) -> tuple[str, str]:
    """(final_decision, answer_draft_override) 반환. override 없으면 ""."""

    # 1. BLOCK — 높은 유해성
    if (
        mod.get("toxicity", 0.0) > TOXICITY_THRESHOLD
        or mod.get("hate", 0.0) > HATE_THRESHOLD
        or mod.get("violence", 0.0) > VIOLENCE_THRESHOLD
        or mod.get("harassment", 0.0) > HARASSMENT_THRESHOLD
    ):
        return FINAL_DECISION_BLOCK, FIXED_BLOCK_MESSAGE

    # 2. REVIEW_QUEUE — 결제 분쟁 · 정책 위반
    if category == "결제" and routing_target == "urgent_alert":
        return FINAL_DECISION_REVIEW, ""

    # 3. MASKING — 개인정보 감지
    if pii.get("pii_detected"):
        masked = pii.get("masked_text", "")
        # 마스킹 후 SAFE_FALLBACK으로 이어지는 재시도
        if retry_count >= MAX_SAFETY_RETRY:
            return FINAL_DECISION_FALLBACK, FIXED_FALLBACK_MESSAGE
        return FINAL_DECISION_MASKING, masked

    # 4. AUTO_RESPONSE — 품질 기준 통과
    if (
        rv.get("factuality", 0.0) >= FACTUALITY_THRESHOLD
        and rv.get("hallucination", 1.0) <= HALLUCINATION_THRESHOLD
    ):
        return FINAL_DECISION_AUTO, ""

    # 5. SAFE_FALLBACK — 근거 부족 · 품질 미달
    if retry_count >= MAX_SAFETY_RETRY:
        return FINAL_DECISION_FALLBACK, FIXED_FALLBACK_MESSAGE
    return FINAL_DECISION_FALLBACK, ""


# ── 노드 ─────────────────────────────────────────────────────────────────────

def safety_layer_node(state: ChatbotState) -> dict:
    draft_id = state.get("draft_id")
    ticket_id = state["ticket_id"]
    answer_draft = state.get("answer_draft", "")
    retry_count = state.get("retry_count", 0)
    category = state.get("category", "")
    routing_target = state.get("routing_target", "")

    llm = _get_llm()
    content = f"답변:\n{answer_draft}"

    rv = _call(llm, _RESPONSE_VALIDATION_PROMPT, content)
    mod = _call(llm, _MODERATION_PROMPT, content)
    pii = _call(llm, _PII_DETECTION_PROMPT, content)

    final_decision, draft_override = _decide(
        rv, mod, pii, category, routing_target, retry_count
    )

    write_safety_results.invoke({
        "payload": {
            "draft_id": draft_id,
            "ticket_id": ticket_id,
            "factuality_score": rv.get("factuality"),
            "hallucination_score": rv.get("hallucination"),
            "toxicity_score": mod.get("toxicity"),
            "hate_score": mod.get("hate"),
            "violence_score": mod.get("violence"),
            "harassment_score": mod.get("harassment"),
            "pii_detected": pii.get("pii_detected", False),
            "policy_violation_score": 1.0 if final_decision == FINAL_DECISION_REVIEW else 0.0,
            "final_decision": final_decision,
        },
    })

    safety_passed = final_decision == FINAL_DECISION_AUTO
    new_retry = retry_count if safety_passed else retry_count + 1

    result: dict = {
        "final_decision": final_decision,
        "safety_passed": safety_passed,
        "pii_detected": pii.get("pii_detected", False),
        "retry_count": new_retry,
    }
    if draft_override:
        result["answer_draft"] = draft_override

    return result
