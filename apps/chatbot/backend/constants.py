from __future__ import annotations

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
    "소중한 의견을 남겨주셔서 감사합니다.\n"
    "보내주신 내용은 운영팀에서 참고할 수 있도록 접수하겠습니다."
)
