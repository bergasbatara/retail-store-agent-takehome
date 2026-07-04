"""OpenAI client construction."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from retail_agent.config import Settings
from retail_agent.exceptions import ValidationError

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI
else:
    OpenAI = Any


def build_openai_client(settings: Settings) -> OpenAI:
    """Build an OpenAI client from runtime settings."""
    if not settings.openai_api_key:
        raise ValidationError("OPENAI_API_KEY is required to run the agent runtime.")

    try:
        from openai import OpenAI as OpenAIClient
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise ValidationError(
            "The `openai` Python package is not installed. Install it to use the chat runtime."
        ) from exc

    return OpenAIClient(api_key=settings.openai_api_key)
