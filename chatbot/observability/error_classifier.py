from __future__ import annotations

from urllib.error import HTTPError, URLError


def classify_error(exc: Exception) -> str:
    """Classify infrastructure/runtime errors into admin-friendly categories."""
    message = str(exc).lower()
    error_type = type(exc).__name__.lower()

    if isinstance(exc, NotImplementedError):
        return "not_implemented"
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection_failed"
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return "auth_failed"
        if exc.code == 404:
            return "endpoint_missing"
        if exc.code == 429:
            return "rate_limited"
        if 500 <= exc.code < 600:
            return "remote_server_error"
        return "http_error"
    if isinstance(exc, URLError):
        reason = str(getattr(exc, "reason", "")).lower()
        if "timed out" in reason or "timeout" in reason:
            return "timeout"
        if "name or service not known" in reason or "temporary failure in name resolution" in reason:
            return "dns_failed"
        if "connection refused" in reason or "could not connect" in reason:
            return "connection_refused"
        return "network_error"

    if "connection refused" in message:
        return "connection_refused"
    if "could not connect" in message or "connection failed" in message:
        return "connection_failed"
    if "temporary failure in name resolution" in message or "name or service not known" in message:
        return "dns_failed"
    if "password authentication failed" in message or "authentication failed" in message:
        return "auth_failed"
    if "does not exist" in message or "undefined table" in message or "no such table" in message:
        return "schema_missing"
    if "duplicate key" in message or "unique constraint" in message:
        return "duplicate_key"
    if "foreign key" in message:
        return "foreign_key_violation"
    if "operationalerror" in error_type:
        return "db_operational_error"
    if "integrityerror" in error_type:
        return "db_integrity_error"

    return "unknown"
