"""Normalization helpers for Korean-safe document processing."""

from __future__ import annotations

import re
import unicodedata


_ZERO_WIDTH_TRANSLATION = {
    ord("\ufeff"): None,
    ord("\u200b"): None,
    ord("\u200c"): None,
    ord("\u200d"): None,
    ord("\u2060"): None,
}
_HORIZONTAL_WS_RE = re.compile(r"[^\S\n]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_DECORATION_LINE_RE = re.compile(r"^[\-=*_~#]{4,}$")


def _strip_control_characters(text: str) -> str:
    allowed = {"\n", "\t"}
    pieces: list[str] = []
    for char in text:
        if char in allowed:
            pieces.append(char)
            continue
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        pieces.append(char)
    return "".join(pieces)


def normalize_document_text(raw_text: str) -> str:
    """Normalize text while keeping Korean and search-relevant symbols intact."""

    text = unicodedata.normalize("NFC", raw_text or "")
    text = text.translate(_ZERO_WIDTH_TRANSLATION)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = _strip_control_characters(text)

    normalized_lines: list[str] = []
    for line in text.split("\n"):
        compact = _HORIZONTAL_WS_RE.sub(" ", line).strip()
        if _DECORATION_LINE_RE.fullmatch(compact):
            continue
        normalized_lines.append(compact)

    text = "\n".join(normalized_lines)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()
