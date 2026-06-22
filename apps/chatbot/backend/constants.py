from __future__ import annotations

# workflow와 safety layer가 공유하는 기준값이다.
MAX_SAFETY_RETRY = 2
MAX_MASKING_RETRY = 2

# Development/demo fallback used only when a caller does not provide an authenticated user_id.
# Production clients should pass the logged-in user's real user_id from the login flow.
DEFAULT_DEMO_USER_ID = 1

ROUTING_TARGET = ["rag_reply", "payment_agent", "bug_agent", "faq_agent", "voc_agent"]
CATEGORY = ["payment", "bug", "faq", "voc"]

# Safety thresholds are conservative operating guardrails for the rule-based grounding check
# plus OpenAI moderation. They should be recalibrated with regression/eval datasets before
# being treated as product-quality policy limits.
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
