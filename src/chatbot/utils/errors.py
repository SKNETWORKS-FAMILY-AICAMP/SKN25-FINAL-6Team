from __future__ import annotations


class ChatbotError(Exception):
    """Base exception for chatbot package errors."""


class ExternalServiceError(ChatbotError):
    """Raised when an external dependency such as DB, Slack, or LLM fails."""

