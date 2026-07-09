"""Abstract provider interface for normalized model turns."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from retail_agent.agent.model_protocol import NormalizedAssistantTurn


class ModelProvider(ABC):
    """Provider adapter that normalizes vendor-specific model responses."""

    @abstractmethod
    def submit(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None,
    ) -> NormalizedAssistantTurn:
        """Submit messages and return a provider-agnostic assistant turn."""
