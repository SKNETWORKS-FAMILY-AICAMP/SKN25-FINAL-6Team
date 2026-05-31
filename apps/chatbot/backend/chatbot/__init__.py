"""Expose backend modules under the `chatbot` package path."""

from __future__ import annotations

from pathlib import Path


_CURRENT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _CURRENT_DIR.parent

if str(_BACKEND_ROOT) not in __path__:
    __path__.append(str(_BACKEND_ROOT))
