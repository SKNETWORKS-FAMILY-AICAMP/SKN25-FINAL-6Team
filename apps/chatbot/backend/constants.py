from __future__ import annotations

from utils.config_loader import load_chatbot_yaml


_SAFETY_POLICY = load_chatbot_yaml("safety_policy.yaml")
_THRESHOLDS = _SAFETY_POLICY.get("thresholds") or {}
if not isinstance(_THRESHOLDS, dict):
    raise ValueError("safety_policy.yaml:thresholds must be a mapping")


def _int_policy(key: str) -> int:
    value = _SAFETY_POLICY.get(key)
    if not isinstance(value, int):
        raise ValueError(f"safety_policy.yaml:{key} must be an integer")
    return value


def _float_threshold(key: str) -> float:
    value = _THRESHOLDS.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"safety_policy.yaml:thresholds.{key} must be a number")
    return float(value)


# Development/demo fallback used only when a caller does not provide an authenticated user_id.
# Production clients should pass the logged-in user's real user_id from the login flow.
DEFAULT_DEMO_USER_ID = 1

MAX_SAFETY_RETRY = _int_policy("max_safety_retry")
MAX_MASKING_RETRY = _int_policy("max_masking_retry")

FACTUALITY_THRESHOLD = _float_threshold("factuality")
HALLUCINATION_THRESHOLD = _float_threshold("hallucination")
FACTUALITY_WARN_THRESHOLD = _float_threshold("factuality_warn")
HALLUCINATION_WARN_THRESHOLD = _float_threshold("hallucination_warn")
FACTUALITY_BLOCK_THRESHOLD = _float_threshold("factuality_block")
HALLUCINATION_BLOCK_THRESHOLD = _float_threshold("hallucination_block")
TOXICITY_THRESHOLD = _float_threshold("toxicity")

VOC_FIXED_RESPONSE = str(_SAFETY_POLICY.get("voc_fixed_response") or "").strip()
if not VOC_FIXED_RESPONSE:
    raise ValueError("safety_policy.yaml:voc_fixed_response must be a non-empty string")
