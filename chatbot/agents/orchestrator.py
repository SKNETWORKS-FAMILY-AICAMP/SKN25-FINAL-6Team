from __future__ import annotations

from chatbot.constants import CATEGORY, ROUTING_TARGET
from chatbot.schemas import ChatbotState, OrchestratorOutput
from chatbot.tools.db_tools import write_qa_ticket, write_ticket_analysis
from config import settings


ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestration classifier for a Korean game CS chatbot.

Classify the user's inquiry into exactly one category and one routing target.

Allowed categories:
- 결제: payment, refund, missing paid item, purchase dispute, item delivery after payment
- 인게임버그: gameplay bug, client error, stuck character, crash, gacha or item state bug
- FAQ: general how-to, account/gameplay guidance, common policy or service question
- VOC: suggestion, complaint, praise, feedback, opinion, multi-intent feedback

Allowed routing_target:
- rag_reply: ordinary automated answer can be attempted
- urgent_alert: operator review or high-risk handling is likely needed

Use urgent_alert for payment disputes, refund requests, missing paid items, policy-sensitive
cases, severe bugs, repeated failures, or anything that should be visible to operators.
Return only the structured output requested by the caller."""


def _normalize_text(text: str) -> str:
    """사용자 입력의 앞뒤 공백과 중복 공백을 정리해 분류하기 좋은 형태로 만든다."""
    return " ".join(text.strip().split())


def _keyword_classify(cleaned_content: str) -> tuple[str, str, str]:
    """LLM 분류 실패 시 사용하는 최소한의 키워드 기반 fallback 분류기."""
    # API 키/네트워크/파싱 오류가 나도 데모 흐름이 멈추지 않도록 안전망을 둔다.
    if any(keyword in cleaned_content for keyword in ("결제", "환불", "미지급", "아이템")):
        return "결제", "urgent_alert", "keyword fallback: payment/refund/missing item keyword matched"
    if any(keyword in cleaned_content for keyword in ("버그", "오류", "튕김", "끼임")):
        return "인게임버그", "rag_reply", "keyword fallback: bug/error keyword matched"
    if any(keyword in cleaned_content for keyword in ("건의", "불만", "칭찬", "의견")):
        return "VOC", "rag_reply", "keyword fallback: feedback keyword matched"
    return "FAQ", "rag_reply", "keyword fallback: no special keyword matched"


def _classify_with_llm(ticket_id: int, cleaned_content: str) -> OrchestratorOutput:
    """LLM structured output으로 카테고리와 라우팅 타깃을 판단한다."""
    if not settings.openai_api_key or not settings.openai_model:
        raise RuntimeError("OpenAI settings are missing.")

    from langchain_openai import ChatOpenAI

    classifier = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
    ).with_structured_output(OrchestratorOutput)

    return classifier.invoke([
        ("system", ORCHESTRATOR_SYSTEM_PROMPT),
        (
            "user",
            "Classify this ticket.\n"
            f"ticket_id: {ticket_id}\n"
            f"cleaned_content: {cleaned_content}",
        ),
    ])


def _classify(ticket_id: int, cleaned_content: str) -> tuple[str, str, str, str]:
    """LLM 분류를 우선 사용하고, 실패하면 키워드 fallback 결과를 반환한다."""
    try:
        result = _classify_with_llm(ticket_id, cleaned_content)
        return result.category, result.routing_target, "llm", result.reason
    except Exception as exc:
        category, routing_target, reason = _keyword_classify(cleaned_content)
        return category, routing_target, "keyword_fallback", f"{reason}; llm classifier unavailable: {type(exc).__name__}"


def _safe_category(category: str) -> str:
    """LLM이 허용되지 않은 카테고리를 반환했을 때 기본값 FAQ로 보정한다."""
    return category if category in CATEGORY else "FAQ"


def _safe_routing_target(routing_target: str) -> str:
    """LLM이 허용되지 않은 라우팅 값을 반환했을 때 기본값 rag_reply로 보정한다."""
    return routing_target if routing_target in ROUTING_TARGET else "rag_reply"


def orchestrator_node(state: ChatbotState) -> dict:
    """StateGraph의 orchestration 노드.

    사용자 문의를 정리하고 카테고리/라우팅 타깃을 결정한 뒤,
    QA 티켓과 분석 결과를 저장하고 다음 노드가 사용할 state 값을 반환한다.
    """
    ticket_id = state.get("ticket_id") or 1001
    raw_content = state.get("raw_content") or ""
    cleaned_content = state.get("cleaned_content") or _normalize_text(raw_content)
    category, routing_target, classification_method, classification_reason = _classify(ticket_id, cleaned_content)
    category = _safe_category(category)
    routing_target = _safe_routing_target(routing_target)

    write_qa_ticket.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "user_id": state.get("user_id"),
            "account_id": state.get("account_id"),
            "raw_content": raw_content,
            "cleaned_content": cleaned_content,
            "source_type": state.get("source_type"),
        },
    })
    write_ticket_analysis.invoke({
        "payload": {
            "ticket_id": ticket_id,
            "category": category,
            "routing_target": routing_target,
            "classification_method": classification_method,
            "reason": classification_reason,
        },
    })

    return {
        "ticket_id": ticket_id,
        "cleaned_content": cleaned_content,
        "category": category,
        "routing_target": routing_target,
        "classification_method": classification_method,
        "classification_reason": classification_reason,
    }
