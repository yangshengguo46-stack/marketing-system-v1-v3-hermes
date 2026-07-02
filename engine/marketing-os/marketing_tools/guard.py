"""DATA-14: Prompt-injection and malicious content guard.

Web-scraped text is always data, never instructions.  Strip injection
patterns, limit length, and preserve original provenance.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate LLM instruction injection
_INJECTION_PATTERNS = (
    re.compile(r"(?i)\b(ignore\s+(all\s+)?(previous|prior|above|before)\s+(instructions?|prompts?|directives?))\b"),
    re.compile(r"(?i)\b(forget\s+(everything|all)\s+(you\s+(were|have\s+been)\s+)?(told|taught))\b"),
    re.compile(r"(?i)\b(you\s+(are|now|must|should)\s+(now\s+)?(acting?\s+as|pretending?\s+(to\s+be|you\s+are)|a\s+different|someone\s+else))\b"),
    re.compile(r"(?i)\b((override|bypass|skip)\s+(all\s+)?(safety\s+)?(rules?|guidelines?|restrictions?|filters?|policies?))\b"),
    re.compile(r"(?i)\b((system\s*(prompt|message|instruction))\s*[:=])"),
    re.compile(r"(?i)\b((DAN|jailbreak|roleplay)\s*(mode|prompt|attack))\b"),
)

_MAX_TEXT_LENGTH = 100_000
_MIN_TEXT_LENGTH = 2


def filter_injection(text: str) -> tuple[str, bool]:
    """Return (sanitized_text, was_filtered).

    Strips known injection patterns and truncates to max length.
    """
    if not text or not isinstance(text, str):
        return "", True
    text = text.strip()
    if len(text) < _MIN_TEXT_LENGTH:
        return text, False

    was_filtered = False
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            # Replace the injection fragment, keep surrounding text
            text = text[:match.start()] + "[FILTERED]" + text[match.end():]
            was_filtered = True

    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH]
        was_filtered = True

    return text, was_filtered


def guard_content(item: dict[str, Any]) -> dict[str, Any]:
    """Apply injection guard to a source item dict, preserving provenance."""
    title, _ = filter_injection(str(item.get("title", "")))
    item["title"] = title[:500]

    raw_content = item.get("raw_text") or item.get("content") or ""
    if isinstance(raw_content, str) and len(raw_content) > 0:
        clean, filtered = filter_injection(raw_content)
        key = "raw_text" if "raw_text" in item else "content"
        item[key] = clean
        if filtered:
            item.setdefault("guard_actions", []).append("injection_filtered")

    return item


def is_safe_text(text: str) -> bool:
    """Quick safety check: no injection patterns, reasonable length."""
    if not text or not isinstance(text, str):
        return False
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return False
    return len(text) <= _MAX_TEXT_LENGTH
