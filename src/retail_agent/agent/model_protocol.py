"""Provider-agnostic normalized model response types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedToolCall:
    """Normalized tool call extracted from any provider response shape."""

    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass(frozen=True)
class NormalizedAssistantTurn:
    """Provider-agnostic assistant turn consumed by the chat runtime."""

    text: str
    tool_calls: tuple[NormalizedToolCall, ...]
    raw: Any
