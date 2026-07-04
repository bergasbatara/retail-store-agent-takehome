"""OpenAI-backed chat runtime with tool calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from retail_agent.agent.openai_client import build_openai_client
from retail_agent.agent.prompts import system_prompt
from retail_agent.agent.tool_executor import execute_tool_call
from retail_agent.agent.tool_schemas import build_tool_definitions
from retail_agent.cli import AppContext


MAX_HISTORY_MESSAGES = 12


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model response wrapper used by the tool loop."""

    raw: Any


def run_agent_turn(user_text: str, session_id: str, app_context: AppContext) -> str:
    """Run a single agent turn with bounded session memory and tool use."""
    session_memory = app_context.session_state.setdefault(
        session_id,
        {"messages": [], "tool_results": []},
    )
    messages = build_messages(session_memory, user_text)
    tools = build_tool_definitions()
    client = build_openai_client(app_context.settings)
    initial_response = submit_with_tools(
        messages=messages,
        tools=tools,
        client=client,
        model_name=app_context.settings.model_name,
    )
    final_text = run_tool_loop(
        initial_response=initial_response,
        session_memory=session_memory,
        tools=tools,
        client=client,
        model_name=app_context.settings.model_name,
        app_context=app_context,
    )
    session_memory["messages"] = _bounded_messages(
        session_memory.get("messages", [])
        + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": final_text},
        ]
    )
    return final_text


def build_messages(session_memory: dict, user_text: str) -> list[dict]:
    """Build the message list sent to the model."""
    history = session_memory.get("messages", [])
    return [{"role": "system", "content": system_prompt()}, *history, {"role": "user", "content": user_text}]


def submit_with_tools(
    messages: list[dict],
    tools: list[dict],
    client: Any,
    model_name: str,
) -> ModelResponse:
    """Submit a model request with tool definitions."""
    response = client.responses.create(
        model=model_name,
        input=messages,
        tools=tools,
    )
    return ModelResponse(raw=response)


def run_tool_loop(
    initial_response: ModelResponse,
    session_memory: dict,
    tools: list[dict],
    client: Any,
    model_name: str,
    app_context: AppContext,
) -> str:
    """Execute tool calls until the model returns final text."""
    response = initial_response.raw
    accumulated_messages: list[dict] = []

    while True:
        tool_calls = _extract_tool_calls(response)
        final_text = _extract_text(response)
        if not tool_calls:
            if final_text:
                return final_text
            if accumulated_messages:
                return accumulated_messages[-1]["content"]
            return "No response was produced."

        for tool_call in tool_calls:
            arguments = _parse_tool_arguments(tool_call)
            tool_result = execute_tool_call(tool_call["name"], arguments, app_context)
            summarized = summarize_tool_result(tool_result)
            session_memory["tool_results"] = (
                session_memory.get("tool_results", []) + [tool_result]
            )[-10:]
            accumulated_messages.append({"role": "tool", "content": summarized})

            response = client.responses.create(
                model=model_name,
                previous_response_id=_get_response_id(response),
                input=[
                    {
                        "type": "function_call_output",
                        "call_id": tool_call["call_id"],
                        "output": json.dumps(tool_result),
                    }
                ],
                tools=tools,
            )


def summarize_tool_result(tool_result: dict, /) -> str:
    """Create a compact textual summary of a tool result for model context."""
    if tool_result.get("ok"):
        result = tool_result.get("result", {})
        return f"{tool_result['tool']} succeeded: {json.dumps(result, default=str)}"
    error = tool_result.get("error", {})
    return f"{tool_result.get('tool', 'tool')} failed: {error.get('message', 'Unknown error')}"


def _extract_tool_calls(response: Any) -> list[dict[str, str]]:
    output_items = _maybe_get(response, "output") or []
    tool_calls: list[dict[str, str]] = []
    for item in output_items:
        item_type = _maybe_get(item, "type")
        if item_type != "function_call":
            continue
        tool_calls.append(
            {
                "name": _maybe_get(item, "name"),
                "arguments": _maybe_get(item, "arguments") or "{}",
                "call_id": _maybe_get(item, "call_id"),
            }
        )
    return tool_calls


def _extract_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = _maybe_get(response, "output") or []
    text_parts: list[str] = []
    for item in output_items:
        item_type = _maybe_get(item, "type")
        if item_type == "message":
            content = _maybe_get(item, "content") or []
            for part in content:
                part_type = _maybe_get(part, "type")
                if part_type in {"output_text", "text"}:
                    text = _maybe_get(part, "text") or ""
                    if text:
                        text_parts.append(text)
    return "\n".join(text_parts).strip()


def _parse_tool_arguments(tool_call: dict[str, str]) -> dict:
    raw = tool_call.get("arguments", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _get_response_id(response: Any) -> str | None:
    return _maybe_get(response, "id")


def _bounded_messages(messages: list[dict]) -> list[dict]:
    history = [message for message in messages if message.get("role") != "system"]
    return history[-MAX_HISTORY_MESSAGES:]


def _maybe_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
