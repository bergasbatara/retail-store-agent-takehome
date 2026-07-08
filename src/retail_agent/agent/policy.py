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
PSEUDO_TOOL_MARKERS = (
    "<|tool_calls_begin|>",
    "<|tool_call_begin|>",
    "<|tool_sep|>",
    "<|tool_call_end|>",
    "<|tool_calls_end|>",
)
CLARIFICATION_PATTERNS = (
    r"\bwhich color\b",
    r"\bwhich size\b",
    r"\bwhich customer\b",
    r"\bwhich .* did you want\b",
    r"\bplease specify\b",
    r"\bcould you confirm\b",
    r"\bwhat color\b",
    r"\bwhat size\b",
)
ERROR_PATTERNS = (
    r"\bambiguous\b",
    r"\bnot found\b",
    r"\bno .* found\b",
    r"\binsufficient inventory\b",
    r"\bmissing\b",
    r"\bmust provide\b",
    r"\bopen purchase order\b",
    r"\bexceeds\b",
)


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
    if contains_pseudo_tool_markup(final_text):
        return False
    if any(re.search(pattern, normalized) for pattern in BAD_PLAINTEXT_PATTERNS):
        return False
    if INVENTED_DATE_PATTERN.search(final_text):
        return False
    return is_true_clarification_or_error(final_text)


def is_true_clarification_or_error(final_text: str) -> bool:
    """Return True when plain text is a narrow clarification or concrete error."""
    normalized = final_text.strip().lower()
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in CLARIFICATION_PATTERNS):
        return True
    if any(re.search(pattern, normalized) for pattern in ERROR_PATTERNS):
        return True
    return False


def contains_pseudo_tool_markup(final_text: str) -> bool:
    """Return True when the model emitted tool-like markers as plain text."""
    return any(marker in final_text for marker in PSEUDO_TOOL_MARKERS)
