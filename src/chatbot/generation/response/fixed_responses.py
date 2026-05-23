from __future__ import annotations

from chatbot.constants import VOC_FIXED_RESPONSE


SAFE_FALLBACK_RESPONSE = "현재 문의는 자동 답변만으로 정확히 안내드리기 어렵습니다. 담당자가 확인 후 다시 안내드리겠습니다."
BLOCK_RESPONSE = "안전한 상담을 위해 해당 문의에는 자동 응답을 제공하기 어렵습니다."
REVIEW_QUEUE_RESPONSE = "문의가 접수되었습니다. 담당자가 확인 후 안내드리겠습니다."

__all__ = [
    "BLOCK_RESPONSE",
    "REVIEW_QUEUE_RESPONSE",
    "SAFE_FALLBACK_RESPONSE",
    "VOC_FIXED_RESPONSE",
]

