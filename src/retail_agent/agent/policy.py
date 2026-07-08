"""Lightweight request/response policy heuristics for the agent runtime."""

from __future__ import annotations

import re


STATE_CHANGE_PATTERNS = (
    r"\bring up\b",
    r"\bsell\b",
    r"\bprocess return\b",
    r"\breturn\b",
    r"\brefund\b",
    r"\breorder\b",
    r"\brestock\b",
    r"\breceive\b",
    r"\bcreate promotion\b",
    r"\bput\b.*\bon\b.*\boff\b",
)

BAD_PLAINTEXT_PATTERNS = (
    r"\bi(?:\s*'ll|\s+will)\s+process\b",
    r"\blet me confirm\b",
    r"\bone moment\b",
    r"\bi(?:\s*'ll|\s+will)\s+confirm\b",
)

INVENTED_DATE_PATTERN = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def is_state_changing_request(user_text: str) -> bool:
    """Return True when the user appears to request a state mutation."""
    normalized = user_text.lower()
    return any(re.search(pattern, normalized) for pattern in STATE_CHANGE_PATTERNS)


def response_satisfies_policy(
    user_text: str,
    tool_calls: list[dict],
    final_text: str,
) -> bool:
    """Return False for state-changing requests answered without required tool use."""
    if not is_state_changing_request(user_text):
        return True
    if tool_calls:
        return True

    normalized = final_text.strip().lower()
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in BAD_PLAINTEXT_PATTERNS):
        return False
    if INVENTED_DATE_PATTERN.search(final_text):
        return False
    return False
