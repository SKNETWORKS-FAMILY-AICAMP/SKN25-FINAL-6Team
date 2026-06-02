from __future__ import annotations

import re
from typing import Any


PROFANITY_TERMS = (
    "시발",
    "씨발",
    "개새끼",
    "병신",
    "미친놈",
    "좆",
)

PROMPT_INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer message",
    "show me your prompt",
    "이전 지시 무시",
    "시스템 프롬프트",
    "개발자 메시지",
    "프롬프트 보여",
)

def _compile_terms(terms: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)


SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("rrn", re.compile(r"\b\d{6}-?[1-4]\d{6}\b"), "[RRN]"),
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD_NUMBER]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("phone", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"), "[PHONE]"),
    (
        "api_key",
        re.compile(
            r"\b(?:sk|rk|pk|sess|token|key|ghp|github_pat)[_-][A-Za-z0-9_-]{16,}\b",
            re.IGNORECASE,
        ),
        "[TOKEN]",
    ),
    (
        "password",
        re.compile(r"(?i)\b(?:password|passcode|pw)\s*[:=]\s*\S+|(?:비밀번호|암호)\s*[:=]\s*\S+"),
        "[PASSWORD]",
    ),
    (
        "account_id",
        re.compile(r"(?i)\b(?:account_id|user_id|uid)\s*[:=]\s*[A-Za-z0-9_-]{4,}\b"),
        "[ACCOUNT_ID]",
    ),
    ("prompt_injection", _compile_terms(PROMPT_INJECTION_PHRASES), "[PROMPT_INJECTION]"),
    ("profanity", _compile_terms(PROFANITY_TERMS), "[PROFANITY]"),
)


def _append_unique(labels: list[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def preprocess_user_input(raw_content: str | None) -> dict[str, Any]:
    """Mask sensitive user input for runtime LLM use without changing the stored raw query."""
    raw = "" if raw_content is None else str(raw_content)
    masked_content = raw.replace("\x00", "")
    detected_labels: list[str] = []

    for label, pattern, replacement in SENSITIVE_PATTERNS:
        masked_content, count = pattern.subn(replacement, masked_content)
        if count:
            _append_unique(detected_labels, label)

    masked = masked_content != raw

    return {
        "raw_content": raw,
        "masked_content": masked_content,
        "detected_labels": detected_labels,
        "masked": masked,
        "block_required": False,
    }
