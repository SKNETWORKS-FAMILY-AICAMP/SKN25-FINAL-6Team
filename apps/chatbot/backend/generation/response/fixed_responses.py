from __future__ import annotations

from constants import VOC_FIXED_RESPONSE
from utils.config_loader import load_chatbot_yaml


_RESPONSES = load_chatbot_yaml("responses.yaml")


def _response_text(key: str) -> str:
    value = _RESPONSES.get(key)
    if not isinstance(value, str):
        raise ValueError(f"responses.yaml:{key} must be a string")
    return value.strip()


SAFE_FALLBACK_RESPONSE = _response_text("safe_fallback")
PAYMENT_FALLBACK_RESPONSE = _response_text("payment_fallback")
BUG_FALLBACK_RESPONSE = _response_text("bug_fallback")
FAQ_FALLBACK_RESPONSE = _response_text("faq_fallback")
BLOCK_RESPONSE = _response_text("block_response")
REVIEW_REQUIRED_RESPONSE = _response_text("review_required")

_RESPONSE_BY_KEY = {
    "safe_fallback": SAFE_FALLBACK_RESPONSE,
    "payment_fallback": PAYMENT_FALLBACK_RESPONSE,
    "bug_fallback": BUG_FALLBACK_RESPONSE,
    "faq_fallback": FAQ_FALLBACK_RESPONSE,
    "block_response": BLOCK_RESPONSE,
    "review_required": REVIEW_REQUIRED_RESPONSE,
    "voc_fixed": VOC_FIXED_RESPONSE,
}


def _load_category_fallbacks() -> dict[str, str]:
    raw_fallbacks = _RESPONSES.get("category_fallbacks")
    if not isinstance(raw_fallbacks, dict):
        raise ValueError("responses.yaml:category_fallbacks must be a mapping")
    result = {}
    for category, response_key in raw_fallbacks.items():
        if not isinstance(category, str) or not isinstance(response_key, str):
            raise ValueError("responses.yaml:category_fallbacks must map string to string")
        if response_key not in _RESPONSE_BY_KEY:
            raise ValueError(f"Unknown response key in responses.yaml: {response_key}")
        result[category] = _RESPONSE_BY_KEY[response_key]
    return result


CATEGORY_FALLBACK_RESPONSES = _load_category_fallbacks()


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
