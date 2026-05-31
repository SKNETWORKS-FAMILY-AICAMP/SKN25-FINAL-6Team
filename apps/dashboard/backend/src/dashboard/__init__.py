"""Expose backend modules under the legacy `src.dashboard` package path."""

from __future__ import annotations

from pathlib import Path


_CURRENT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _CURRENT_DIR.parents[1]

if str(_BACKEND_ROOT) not in __path__:
    __path__.append(str(_BACKEND_ROOT))
