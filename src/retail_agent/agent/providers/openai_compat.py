"""OpenAI-compatible provider adapter with safe pseudo-tool normalization."""

from __future__ import annotations

import json
import re
from typing import Any

from retail_agent.agent.model_protocol import NormalizedAssistantTurn, NormalizedToolCall
from retail_agent.agent.policy import contains_pseudo_tool_markup
from retail_agent.agent.providers.base import ModelProvider


XML_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.IGNORECASE | re.DOTALL,
)
JSON_TOOL_BLOCK_PATTERN = re.compile(
    r'^\s*\{\s*"name"\s*:\s*"(?P<name>[^"]+)"\s*,\s*"arguments"\s*:\s*(?P<arguments>\{.*\})\s*\}\s*$',
    re.IGNORECASE | re.DOTALL,
)


class OpenAICompatProvider(ModelProvider):
    """Adapter for OpenAI-compatible chat completions responses."""

    def __init__(self, client: Any, model_name: str):
        self._client = client
        self._model_name = model_name

    def submit(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None,
    ) -> NormalizedAssistantTurn:
        request_kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "tools": tools,
        }
        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice

        raw = self._client.chat.completions.create(**request_kwargs)
        raw_text = _extract_raw_text(raw)
        text = _sanitize_text(raw_text)
        tool_calls = _extract_tool_calls(raw)
        if not tool_calls and raw_text:
            tool_calls = _extract_safe_pseudo_tool_calls(raw_text, tools)
            if tool_calls:
                text = ""
        return NormalizedAssistantTurn(
            text=text,
            tool_calls=tuple(tool_calls),
            raw=raw,
        )


def _extract_tool_calls(response: Any) -> list[NormalizedToolCall]:
    choice = _first_choice(response)
    message = _maybe_get(choice, "message")
    raw_tool_calls = _maybe_get(message, "tool_calls") or []
    tool_calls: list[NormalizedToolCall] = []
    for item in raw_tool_calls:
        item_type = _maybe_get(item, "type")
        if item_type not in {None, "function"}:
            continue
        function = _maybe_get(item, "function")
        arguments = _parse_arguments(_maybe_get(function, "arguments"))
        tool_calls.append(
            NormalizedToolCall(
                name=str(_maybe_get(function, "name") or ""),
                arguments=arguments,
                call_id=str(_maybe_get(item, "id") or ""),
            )
        )
    return tool_calls


def _extract_raw_text(response: Any) -> str:
    choice = _first_choice(response)
    message = _maybe_get(choice, "message")
    content = _maybe_get(message, "content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
        return "\n".join(part for part in text_parts if part).strip()
    return ""


def _sanitize_text(text: str) -> str:
    if contains_pseudo_tool_markup(text):
        return ""
    return text


def _extract_safe_pseudo_tool_calls(
    text: str,
    tools: list[dict[str, Any]],
) -> list[NormalizedToolCall]:
    allowed_schemas = _tool_schema_map(tools)
    payloads: list[dict[str, Any]] = []

    for match in XML_TOOL_CALL_PATTERN.finditer(text):
        payload = _parse_json_block(match.group(1))
        if isinstance(payload, dict):
            payloads.append(payload)

    if not payloads:
        match = JSON_TOOL_BLOCK_PATTERN.match(text)
        if match:
            payload = _parse_json_block(text)
            if isinstance(payload, dict):
                payloads.append(payload)

    safe_calls: list[NormalizedToolCall] = []
    for index, payload in enumerate(payloads, start=1):
        name = str(payload.get("name") or "")
        arguments = payload.get("arguments")
        if name not in allowed_schemas:
            continue
        if not isinstance(arguments, dict):
            continue
        schema = allowed_schemas[name]
        if not _arguments_match_schema(arguments, schema):
            continue
        safe_calls.append(
            NormalizedToolCall(
                name=name,
                arguments=arguments,
                call_id=f"pseudo-call-{index}",
            )
        )
    return safe_calls


def _tool_schema_map(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if tool.get("type") != "function":
            continue
        function = tool.get("function") or {}
        name = function.get("name")
        parameters = function.get("parameters")
        if isinstance(name, str) and isinstance(parameters, dict):
            schemas[name] = parameters
    return schemas


def _arguments_match_schema(arguments: dict[str, Any], schema: dict[str, Any]) -> bool:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return False

    required = schema.get("required", [])
    if isinstance(required, list):
        for key in required:
            if key not in arguments:
                return False

    additional_properties = schema.get("additionalProperties", True)
    if additional_properties is False:
        for key in arguments:
            if key not in properties:
                return False

    return True


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_json_block(raw) or {}
    return {}


def _parse_json_block(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_choice(response: Any) -> Any:
    choices = _maybe_get(response, "choices") or []
    return choices[0] if choices else None


def _maybe_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
