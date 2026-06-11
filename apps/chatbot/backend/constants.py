from __future__ import annotations

# workflow와 safety layer가 함께 쓰는 공통 기준값이다.
# category/route 이름을 바꿀 때는 라우팅 코드보다 이 상수를 먼저 확인한다.
MAX_SAFETY_RETRY = 2
MAX_MASKING_RETRY = 2

ROUTING_TARGET = ["rag_reply", "urgent_alert"]
CATEGORY = ["payment", "bug", "faq", "voc"]

FACTUALITY_THRESHOLD = 0.8
HALLUCINATION_THRESHOLD = 0.3
FACTUALITY_WARN_THRESHOLD = 0.5
HALLUCINATION_WARN_THRESHOLD = 0.5
FACTUALITY_BLOCK_THRESHOLD = 0.3
HALLUCINATION_BLOCK_THRESHOLD = 0.7
TOXICITY_THRESHOLD = 0.7

VOC_FIXED_RESPONSE = (
    "소중한 의견 감사합니다. 의견 반영하여 더 나은 서비스를 제공하도록 하겠습니다."
)
