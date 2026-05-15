from __future__ import annotations

MAX_SAFETY_RETRY = 2
ROUTING_TARGET = ["rag_reply", "urgent_alert"]
CATEGORY = ["결제", "인게임버그", "FAQ", "VOC"]

# Response Validation 임계값
FACTUALITY_THRESHOLD = 0.8
HALLUCINATION_THRESHOLD = 0.3

# Moderation 임계값
TOXICITY_THRESHOLD = 0.7
HATE_THRESHOLD = 0.7
VIOLENCE_THRESHOLD = 0.7
HARASSMENT_THRESHOLD = 0.7

# Safety final_decision 값
FINAL_DECISION_AUTO = "AUTO_RESPONSE"
FINAL_DECISION_FALLBACK = "SAFE_FALLBACK"
FINAL_DECISION_MASKING = "MASKING"
FINAL_DECISION_BLOCK = "BLOCK_RESPONSE"
FINAL_DECISION_REVIEW = "REVIEW_QUEUE"

# 고정 안내문
FIXED_FALLBACK_MESSAGE = (
    "죄송합니다. 현재 정확한 답변을 드리기 어렵습니다. "
    "고객센터로 문의해 주시면 빠르게 도움 드리겠습니다."
)
FIXED_BLOCK_MESSAGE = (
    "해당 내용은 답변이 어렵습니다. 고객센터로 문의해 주세요."
)
