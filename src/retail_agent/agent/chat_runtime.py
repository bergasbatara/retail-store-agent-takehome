"""OpenAI-backed chat runtime with tool calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from retail_agent.agent.openai_client import build_openai_client
from retail_agent.agent.policy import is_state_changing_request, response_satisfies_policy
from retail_agent.agent.prompts import system_prompt
from retail_agent.agent.tool_executor import execute_tool_call
from retail_agent.agent.tool_schemas import build_tool_definitions
from retail_agent.cli import AppContext
from retail_agent.db.repositories import SessionRepository
from retail_agent.session.memory import (
    SessionMemory,
    inject_memory_hints,
    load_session_memory,
    save_session_memory,
    update_memory_from_tool_result,
)


MAX_HISTORY_MESSAGES = 12
MAX_POLICY_RETRIES = 2


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model response wrapper used by the tool loop."""

    raw: Any


def run_agent_turn(user_text: str, session_id: str, app_context: AppContext) -> str:
    """Run a single agent turn with bounded session memory and tool use."""
    session_memory = app_context.session_state.setdefault(
        session_id,
        {"messages": [], "tool_results": [], "memory": None},
    )
    repo = SessionRepository(app_context.conn)
    structured_memory = session_memory.get("memory")
    if not isinstance(structured_memory, SessionMemory):
        structured_memory = load_session_memory(session_id, repo)
        session_memory["memory"] = structured_memory

    messages = build_messages(session_memory, user_text, structured_memory)
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
        messages=messages,
        session_memory=session_memory,
        tools=tools,
        client=client,
        model_name=app_context.settings.model_name,
        app_context=app_context,
        structured_memory=structured_memory,
        session_id=session_id,
        session_repo=repo,
    )
    session_memory["messages"] = _bounded_messages(
        session_memory.get("messages", [])
        + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": final_text},
        ]
    )
    return final_text


def build_messages(
    session_memory: dict,
    user_text: str,
    structured_memory: SessionMemory,
) -> list[dict]:
    """Build the message list sent to the model."""
    history = session_memory.get("messages", [])
    current_date = date.today().isoformat()
    return [
        {"role": "system", "content": system_prompt(current_date)},
        {"role": "system", "content": inject_memory_hints(structured_memory)},
        *history,
        {"role": "user", "content": user_text},
    ]


def submit_with_tools(
    messages: list[dict],
    tools: list[dict],
    client: Any,
    model_name: str,
) -> ModelResponse:
    """Submit a chat-completions request with tool definitions."""
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tools,
    )
    return ModelResponse(raw=response)


def run_tool_loop(
    initial_response: ModelResponse,
    messages: list[dict],
    session_memory: dict,
    tools: list[dict],
    client: Any,
    model_name: str,
    app_context: AppContext,
    structured_memory: SessionMemory,
    session_id: str,
    session_repo: SessionRepository,
) -> str:
    """Execute tool calls until the model returns final text."""
    response = initial_response.raw
    conversation_messages = list(messages)
    original_user_text = next(
        (str(message["content"]) for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    policy_retry_count = 0
    used_tool_this_turn = False

    while True:
        tool_calls = _extract_tool_calls(response)
        final_text = _extract_text(response)
        if not tool_calls:
            effective_tool_calls = tool_calls or ([{"name": "completed_tool"}] if used_tool_this_turn else [])
            if not response_satisfies_policy(original_user_text, effective_tool_calls, final_text):
                if policy_retry_count < MAX_POLICY_RETRIES:
                    assistant_message = _assistant_message_from_response(response)
                    if assistant_message is not None:
                        conversation_messages.append(assistant_message)
                    conversation_messages.append(build_tool_retry_message(original_user_text))
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=conversation_messages,
                        tools=tools,
                    )
                    policy_retry_count += 1
                    continue
                return _policy_failure_message(original_user_text)
            if final_text:
                return final_text
            if conversation_messages and conversation_messages[-1].get("role") == "assistant":
                return str(conversation_messages[-1].get("content", ""))
            return "No response was produced."

        assistant_message = _assistant_message_from_response(response)
        if assistant_message is not None:
            conversation_messages.append(assistant_message)

        for tool_call in tool_calls:
            arguments = _parse_tool_arguments(tool_call)
            tool_result = execute_tool_call(tool_call["name"], arguments, app_context)
            summarized = summarize_tool_result(tool_result)
            used_tool_this_turn = True
            session_memory["tool_results"] = (
                session_memory.get("tool_results", []) + [tool_result]
            )[-10:]
            structured_memory = update_memory_from_tool_result(structured_memory, tool_result)
            session_memory["memory"] = structured_memory
            if tool_result.get("ok"):
                save_session_memory(session_id, structured_memory, session_repo)
            conversation_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["call_id"],
                    "content": json.dumps(tool_result, default=str),
                }
            )
            _ = summarized

        response = client.chat.completions.create(
            model=model_name,
            messages=conversation_messages,
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
    choice = _first_choice(response)
    message = _maybe_get(choice, "message")
    raw_tool_calls = _maybe_get(message, "tool_calls") or []
    tool_calls: list[dict[str, str]] = []
    for item in raw_tool_calls:
        item_type = _maybe_get(item, "type")
        if item_type not in {None, "function"}:
            continue
        function = _maybe_get(item, "function")
        tool_calls.append(
            {
                "name": _maybe_get(function, "name"),
                "arguments": _maybe_get(function, "arguments") or "{}",
                "call_id": _maybe_get(item, "id"),
            }
        )
    return tool_calls


def _extract_text(response: Any) -> str:
    choice = _first_choice(response)
    message = _maybe_get(choice, "message")
    content = _maybe_get(message, "content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
        return "\n".join(part for part in text_parts if part).strip()
    return ""


def _parse_tool_arguments(tool_call: dict[str, str]) -> dict:
    raw = tool_call.get("arguments", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _bounded_messages(messages: list[dict]) -> list[dict]:
    history = [message for message in messages if message.get("role") != "system"]
    return history[-MAX_HISTORY_MESSAGES:]


def _assistant_message_from_response(response: Any) -> dict[str, Any] | None:
    choice = _first_choice(response)
    message = _maybe_get(choice, "message")
    if message is None:
        return None

    content = _maybe_get(message, "content")
    tool_calls = _maybe_get(message, "tool_calls")
    assistant_message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        assistant_message["content"] = content
    else:
        assistant_message["content"] = ""
    if tool_calls:
        assistant_message["tool_calls"] = [
            {
                "id": _maybe_get(tool_call, "id"),
                "type": _maybe_get(tool_call, "type") or "function",
                "function": {
                    "name": _maybe_get(_maybe_get(tool_call, "function"), "name"),
                    "arguments": _maybe_get(_maybe_get(tool_call, "function"), "arguments"),
                },
            }
            for tool_call in tool_calls
        ]
    return assistant_message


def _first_choice(response: Any) -> Any:
    choices = _maybe_get(response, "choices") or []
    return choices[0] if choices else None


def _maybe_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _policy_failure_message(user_text: str) -> str:
    if is_state_changing_request(user_text):
        return (
            "The model did not use the required tool for this state-changing request. "
            "Retry with a tool-calling-capable response policy."
        )
    return "The model response did not satisfy runtime policy."


def build_tool_retry_message(user_text: str) -> dict[str, str]:
    """Build a corrective system instruction after a policy-violating response."""
    return {
        "role": "system",
        "content": (
            "The previous response violated runtime policy. "
            "This request is a state-changing action and must use the appropriate tool now if it is actionable. "
            "Do not ask for confirmation, do not invent dates or IDs, and do not answer with plain text only. "
            f"Original user request: {user_text}"
        ),
    }
