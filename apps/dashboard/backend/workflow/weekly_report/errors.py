"""Shared exceptions for weekly dashboard report helpers."""

from __future__ import annotations


class SlackReportError(RuntimeError):
    """Raised when Slack rejects or cannot accept the report upload."""
