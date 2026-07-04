"""General-purpose terminal message renderers."""

from __future__ import annotations

from typing import Any


def render_clarification(message: str) -> str:
    """Render a compact clarification prompt."""
    return f"Need clarification: {message.strip()}"


def render_success_summary(payload: dict) -> str:
    """Render a compact deterministic summary for a successful payload."""
    parts: list[str] = []
    for key in sorted(payload):
        parts.append(f"{key}={_render_value(payload[key])}")
    return "Success: " + ", ".join(parts) if parts else "Success."


def _render_value(value: Any) -> str:
    if isinstance(value, dict):
        inner = ", ".join(
            f"{key}:{_render_value(value[key])}"
            for key in sorted(value)
        )
        return "{" + inner + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_render_value(item) for item in value) + "]"
    return str(value)
