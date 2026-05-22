"""Shared redaction helpers for observability output."""

from __future__ import annotations

from typing import Any
import re

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "user_id",
    "email",
)

REDACTED = "[REDACTED]"
MAX_TEXT_LENGTH = 500
SECRET_PATTERNS = (
    re.compile(r"\b[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*\S+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9._-]+"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+", re.I),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
)


def sanitize_observability_value(key: str, value: Any) -> Any:
    """Redact sensitive keyed values and bound free-text log payloads."""
    key_lower = key.lower()
    if any(part in key_lower for part in SENSITIVE_KEY_PARTS):
        return REDACTED

    if isinstance(value, dict):
        return {
            str(child_key): sanitize_observability_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_observability_value(key, item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_observability_value(key, item) for item in value)
    if isinstance(value, str):
        sanitized = value
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub(REDACTED, sanitized)
        if len(sanitized) > MAX_TEXT_LENGTH:
            sanitized = sanitized[:MAX_TEXT_LENGTH] + "...[truncated]"
        return sanitized

    return value


def contains_sensitive_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)
