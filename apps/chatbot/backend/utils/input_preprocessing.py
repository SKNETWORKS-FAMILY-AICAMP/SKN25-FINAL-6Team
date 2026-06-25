from __future__ import annotations

import re
from typing import Any

from utils.config_loader import load_chatbot_yaml

try:
    from korcen import korcen as korcen_filter
except ModuleNotFoundError:
    korcen_filter = None


INPUT_PREPROCESSING_RULES = "rules/input_preprocessing.yaml"


def _regex_flags(config: dict[str, Any]) -> int:
    return re.IGNORECASE if config.get("ignore_case") else 0


def _compile_pattern(config: dict[str, Any]) -> re.Pattern[str]:
    pattern = config.get("pattern")
    if not isinstance(pattern, str):
        raise ValueError("input preprocessing pattern must include a string 'pattern'")
    return re.compile(pattern, _regex_flags(config))


def _load_prompt_injection_patterns() -> tuple[re.Pattern[str], ...]:
    raw_patterns = load_chatbot_yaml(INPUT_PREPROCESSING_RULES).get("prompt_injection_patterns")
    if not isinstance(raw_patterns, list):
        raise ValueError("rules/input_preprocessing.yaml:prompt_injection_patterns must be a list")
    return tuple(_compile_pattern(item) for item in raw_patterns if isinstance(item, dict))


def _load_sensitive_patterns() -> tuple[tuple[str, re.Pattern[str], str], ...]:
    raw_patterns = load_chatbot_yaml(INPUT_PREPROCESSING_RULES).get("sensitive_patterns")
    if not isinstance(raw_patterns, list):
        raise ValueError("rules/input_preprocessing.yaml:sensitive_patterns must be a list")
    compiled = []
    for item in raw_patterns:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        replacement = item.get("replacement")
        if not isinstance(label, str) or not isinstance(replacement, str):
            raise ValueError("sensitive pattern must include string label and replacement")
        compiled.append((label, _compile_pattern(item), replacement))
    return tuple(compiled)


PROMPT_INJECTION_PATTERNS = _load_prompt_injection_patterns()
SENSITIVE_PATTERNS = _load_sensitive_patterns()

def _append_unique(labels: list[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def _mask_profanity(text: str) -> tuple[str, bool]:
    # korcen으로 욕설 구간을 감지하고, 감지된 구간만 [PROFANITY]로 치환한다.
    if korcen_filter is None:
        return text, False

    marker = "\ue000"
    highlighted = korcen_filter.highlight_profanity(text, highlight_char=marker)
    if highlighted == text:
        return text, False

    pattern = re.compile(f"{re.escape(marker)}.*?{re.escape(marker)}")
    return pattern.sub("[PROFANITY]", highlighted), True


def _mask_prompt_injection(text: str) -> tuple[str, bool]:
    # prompt injection 의심 표현은 답변 차단이 아니라 [PROMPT_INJECTION] 마스킹과 label 기록만 수행한다.
    masked_text = text
    detected = False
    for pattern in PROMPT_INJECTION_PATTERNS:
        masked_text, count = pattern.subn("[PROMPT_INJECTION]", masked_text)
        detected = detected or count > 0
    return masked_text, detected


def preprocess_user_input(raw_content: str | None) -> dict[str, Any]:
    # 1단계: 원문은 보존하고, 런타임 LLM에 넘길 masked_content만 별도로 만든다.
    raw = "" if raw_content is None else str(raw_content)
    masked_content = raw.replace("\x00", "")
    detected_labels: list[str] = []

    # 2단계: 개인정보/인증정보 regex를 먼저 적용한다.
    for label, pattern, replacement in SENSITIVE_PATTERNS:
        masked_content, count = pattern.subn(replacement, masked_content)
        if count:
            _append_unique(detected_labels, label)

    # 3단계: 욕설은 korcen으로 감지해서 label과 마스킹 결과에 반영한다.
    masked_content, profanity_detected = _mask_profanity(masked_content)
    if profanity_detected:
        _append_unique(detected_labels, "profanity")

    # 4단계: prompt injection 의심 regex를 적용하고, 차단 대신 마스킹 label만 남긴다.
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
