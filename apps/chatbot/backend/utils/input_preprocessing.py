from __future__ import annotations

import re
from typing import Any

from korcen import korcen as korcen_filter


PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(ignore|forget|bypass|override|disregard)\b.{0,40}\b(instruction|rule|policy|safety|guardrail)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(show|print|reveal|leak|display|tell me)\b.{0,40}\b(prompt|instruction|developer message|system message)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(system prompt|developer message|hidden prompt|internal prompt|initial instruction)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(do not refuse|don't refuse|bypass safety|disable safety|jailbreak|DAN mode)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\.env|api key|secret|access token|private key|db password|database password)\b.{0,40}\b(show|print|reveal|leak|display|tell me)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(이전|앞의|위의|기존).{0,12}(지시|명령|규칙|정책).{0,12}(무시|잊어|삭제|취소)(하고|해|해줘|해라|하세요)?"),
    re.compile(r"(시스템|개발자|숨겨진|내부).{0,12}(프롬프트|메시지|지시문|규칙).{0,12}(보여|출력|알려|공개)(줘|해줘|해라|하세요)?"),
    re.compile(r"(안전|보안|검열|정책).{0,12}(무시|우회|해제|끄고|끄기)(해|해줘|해라|하세요)?"),
    re.compile(r"(\.env|API\s*키|토큰|시크릿|DB\s*비밀번호|환경변수).{0,12}(보여|출력|알려|공개)(줘|해줘|해라|하세요)?"),
)


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
)


def _append_unique(labels: list[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def _mask_profanity(text: str) -> tuple[str, bool]:
    marker = "\ue000"
    highlighted = korcen_filter.highlight_profanity(text, highlight_char=marker)
    if highlighted == text:
        return text, False

    pattern = re.compile(f"{re.escape(marker)}.*?{re.escape(marker)}")
    return pattern.sub("[PROFANITY]", highlighted), True


def _mask_prompt_injection(text: str) -> tuple[str, bool]:
    masked_text = text
    detected = False
    for pattern in PROMPT_INJECTION_PATTERNS:
        masked_text, count = pattern.subn("[PROMPT_INJECTION]", masked_text)
        detected = detected or count > 0
    return masked_text, detected


def preprocess_user_input(raw_content: str | None) -> dict[str, Any]:
    """Mask sensitive user input for runtime LLM use without changing the stored raw query."""
    raw = "" if raw_content is None else str(raw_content)
    masked_content = raw.replace("\x00", "")
    detected_labels: list[str] = []

    for label, pattern, replacement in SENSITIVE_PATTERNS:
        masked_content, count = pattern.subn(replacement, masked_content)
        if count:
            _append_unique(detected_labels, label)

    masked_content, profanity_detected = _mask_profanity(masked_content)
    if profanity_detected:
        _append_unique(detected_labels, "profanity")

    masked_content, prompt_injection_detected = _mask_prompt_injection(masked_content)
    if prompt_injection_detected:
        _append_unique(detected_labels, "prompt_injection")

    masked = masked_content != raw

    return {
        "raw_content": raw,
        "masked_content": masked_content,
        "detected_labels": detected_labels,
        "masked": masked,
        "block_required": False,
    }
