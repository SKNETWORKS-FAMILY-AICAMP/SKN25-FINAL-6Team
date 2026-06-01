"""Expose `common` modules under the legacy `src.common` package path."""

from __future__ import annotations

from pathlib import Path


_CURRENT_DIR = Path(__file__).resolve().parent
_LEGACY_COMMON_DIR = _CURRENT_DIR.parents[1] / "common"

if str(_LEGACY_COMMON_DIR) not in __path__:
    __path__.append(str(_LEGACY_COMMON_DIR))
