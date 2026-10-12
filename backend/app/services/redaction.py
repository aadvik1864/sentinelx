"""Best-effort credential redaction, not proof that logs contain no sensitive/PII data."""

import re

SECRET_KEY = re.compile(
    r"password|passwd|secret|token|authorization|cookie|api.?key|credential|private.?key", re.I
)
PATTERNS = [
    (
        re.compile(
            r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"
        ),
        "[redacted-private-key]",
    ),
    (re.compile(r"(?i)\b(?:Bearer|Basic)\s+[a-zA-Z0-9._~+/=-]+"), "[redacted-authorization]"),
    (
        re.compile(
            r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1=[redacted]",
    ),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[redacted-jwt]"),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sxcol_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
        ),
        "[redacted-key]",
    ),
    (re.compile(r"(?i)(https?://)[^/\s@]+@"), r"\1[redacted]@"),
    (re.compile(r"(?i)(https?://[^\s?\"'<>]+)\?[^\s\"'<>]*"), r"\1?[redacted-query]"),
]


def redact(value, depth=0):
    if depth > 20:
        return "[redacted-nested-value]"
    if isinstance(value, dict):
        return {
            key: "[redacted]" if SECRET_KEY.search(str(key)) else redact(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value]
    if isinstance(value, str):
        for pattern, replacement in PATTERNS:
            value = pattern.sub(replacement, value)
    return value
