from __future__ import annotations

from chatbot.constants import VOC_FIXED_RESPONSE


SAFE_FALLBACK_RESPONSE = (
    "현재 문의 내용만으로는 정확한 안내를 드리기 어렵습니다. "
    "필요한 경우 담당자가 확인 후 다시 안내드리겠습니다."
)
PAYMENT_FALLBACK_RESPONSE = (
    "결제 관련 문의는 계정 및 결제 내역 확인이 필요합니다. "
    "담당자가 결제 상태와 지급 여부를 확인할 수 있도록 접수하겠습니다."
)
BUG_FALLBACK_RESPONSE = (
    "게임 이용 중 발생한 문제는 기기 환경과 발생 상황 확인이 필요합니다. "
    "담당자가 재현 정보와 로그를 확인할 수 있도록 접수하겠습니다."
)
FAQ_FALLBACK_RESPONSE = SAFE_FALLBACK_RESPONSE
BLOCK_RESPONSE = (
    "안전한 상담을 위해 해당 문의에는 자동 답변을 제공하기 어렵습니다. "
    "필요한 경우 담당자가 확인 후 안내드리겠습니다."
)
REVIEW_REQUIRED_RESPONSE = "문의가 접수되었습니다. 담당자가 확인 후 안내드리겠습니다."

CATEGORY_FALLBACK_RESPONSES = {
    "payment": PAYMENT_FALLBACK_RESPONSE,
    "bug": BUG_FALLBACK_RESPONSE,
    "faq": FAQ_FALLBACK_RESPONSE,
    "voc": VOC_FIXED_RESPONSE,
    "결제": PAYMENT_FALLBACK_RESPONSE,
    "버그": BUG_FALLBACK_RESPONSE,
    "인게임 버그": BUG_FALLBACK_RESPONSE,
    "FAQ": FAQ_FALLBACK_RESPONSE,
    "VOC": VOC_FIXED_RESPONSE,
}


def fallback_response_for_category(category: str | None) -> str:
    return CATEGORY_FALLBACK_RESPONSES.get(str(category or ""), SAFE_FALLBACK_RESPONSE)


__all__ = [
    "BLOCK_RESPONSE",
    "BUG_FALLBACK_RESPONSE",
    "CATEGORY_FALLBACK_RESPONSES",
    "FAQ_FALLBACK_RESPONSE",
    "PAYMENT_FALLBACK_RESPONSE",
    "REVIEW_REQUIRED_RESPONSE",
    "SAFE_FALLBACK_RESPONSE",
    "VOC_FIXED_RESPONSE",
    "fallback_response_for_category",
]
