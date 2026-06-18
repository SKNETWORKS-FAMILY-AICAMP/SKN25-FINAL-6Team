"""Normalization helpers for Korean-safe document processing."""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser


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
_HTML_TAG_RE = re.compile(r"<[A-Za-z][^>]*>|</[A-Za-z][^>]*>")


class _HTMLTextExtractor(HTMLParser):
    """Extract visible FAQ text while preserving paragraph boundaries."""

    _PARAGRAPH_TAGS = {"p", "div", "li"}
    _LINE_BREAK_TAGS = {"br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        if tag in self._LINE_BREAK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._PARAGRAPH_TAGS:
            self._append_paragraph_break()

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)

    def _append_newline(self) -> None:
        if self._parts and not self._parts[-1].endswith("\n"):
            self._parts.append("\n")

    def _append_paragraph_break(self) -> None:
        if not self._parts:
            return
        if not "".join(self._parts).strip():
            return
        current = self._parts[-1]
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self._parts.append("\n")
        else:
            self._parts.append("\n\n")


def _strip_html(text: str) -> str:
    """Strip HTML only when the source looks like HTML; plain text passes through."""

    if not _HTML_TAG_RE.search(text):
        return text

    parser = _HTMLTextExtractor()
    parser.feed(html.unescape(text))
    parser.close()
    return parser.get_text()


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

    text = _strip_html(raw_text or "")
    text = unicodedata.normalize("NFC", text)
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
