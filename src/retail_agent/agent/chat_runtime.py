"""Provider-agnostic chat runtime with normalized tool calls."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from retail_agent.agent.openai_client import build_openai_client
from retail_agent.agent.model_protocol import NormalizedAssistantTurn, NormalizedToolCall
from retail_agent.agent.policy import (
    is_state_changing_request,
    is_true_clarification_or_error,
    response_satisfies_policy,
)
from retail_agent.agent.prompts import system_prompt
from retail_agent.agent.providers.base import ModelProvider
from retail_agent.agent.providers.openai_compat import OpenAICompatProvider
from retail_agent.agent.tool_executor import execute_tool_call
from retail_agent.agent.tool_schemas import build_tool_definitions
from retail_agent.cli import AppContext
from retail_agent.db.repositories import SessionRepository
from retail_agent.presenters.messages import render_clarification
from retail_agent.presenters.tool_results import (
    DETERMINISTIC_RESULT_TOOLS,
    STATE_CHANGING_TOOLS,
    render_tool_result,
    render_state_change_result,
)
from retail_agent.session.memory import (
    SessionMemory,
    inject_memory_hints,
    load_session_memory,
    save_session_memory,
    update_memory_from_tool_result,
)


MAX_HISTORY_MESSAGES = 12
MAX_POLICY_RETRIES = 2


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
    provider = OpenAICompatProvider(client, app_context.settings.model_name)
    require_tool_choice = is_state_changing_request(user_text)
    initial_response = submit_with_tools(
        messages=messages,
        tools=tools,
        provider=provider,
        tool_choice=_tool_choice_for_request(require_tool_choice),
    )
    final_text = run_tool_loop(
        initial_response=initial_response,
        messages=messages,
        session_memory=session_memory,
        tools=tools,
        provider=provider,
        app_context=app_context,
        structured_memory=structured_memory,
        session_id=session_id,
        session_repo=repo,
        require_tool_choice=require_tool_choice,
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
    provider: ModelProvider,
    tool_choice: str | None = None,
) -> NormalizedAssistantTurn:
    """Submit a provider request with tool definitions."""
    return provider.submit(messages=messages, tools=tools, tool_choice=tool_choice)


def run_tool_loop(
    initial_response: NormalizedAssistantTurn,
    messages: list[dict],
    session_memory: dict,
    tools: list[dict],
    provider: ModelProvider,
    app_context: AppContext,
    structured_memory: SessionMemory,
    session_id: str,
    session_repo: SessionRepository,
    require_tool_choice: bool,
) -> str:
    """Execute tool calls until the model returns final text."""
    response = initial_response
    conversation_messages = list(messages)
    original_user_text = next(
        (str(message["content"]) for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    policy_retry_count = 0
    used_tool_this_turn = False
    successful_state_change_results: list[dict[str, Any]] = []
    successful_deterministic_result: dict[str, Any] | None = None
    last_tool_error_result: dict[str, Any] | None = None
    failed_state_change_result: dict[str, Any] | None = None

    while True:
        tool_calls = list(response.tool_calls)
        final_text = response.text
        if not tool_calls:
            effective_tool_calls = tool_calls or ([{"name": "completed_tool"}] if used_tool_this_turn else [])
            if not response_satisfies_policy(original_user_text, effective_tool_calls, final_text):
                if policy_retry_count < MAX_POLICY_RETRIES:
                    assistant_message = _assistant_message_from_response(response)
                    if assistant_message is not None:
                        conversation_messages.append(assistant_message)
                    conversation_messages.append(build_tool_retry_message(original_user_text))
                    response = provider.submit(
                        messages=conversation_messages,
                        tools=tools,
                        tool_choice=_tool_choice_for_request(require_tool_choice),
                    )
                    policy_retry_count += 1
                    continue
                return _policy_failure_message(original_user_text)
            if failed_state_change_result is not None:
                return _render_tool_error(failed_state_change_result)
            if successful_state_change_results:
                return render_state_change_result(successful_state_change_results[-1])
            if successful_deterministic_result is not None:
                return render_tool_result(successful_deterministic_result)
            if last_tool_error_result is not None:
                return _render_tool_error(last_tool_error_result)
            if require_tool_choice and is_true_clarification_or_error(final_text):
                return _render_state_change_clarification(final_text)
            if final_text:
                return final_text
            if require_tool_choice:
                return _policy_failure_message(original_user_text)
            if conversation_messages and conversation_messages[-1].get("role") == "assistant":
                return str(conversation_messages[-1].get("content", ""))
            return "No response was produced."

        assistant_message = _assistant_message_from_response(response)
        if assistant_message is not None:
            conversation_messages.append(assistant_message)

        for tool_call in tool_calls:
            tool_result = execute_tool_call(tool_call.name, tool_call.arguments, app_context)
            summarized = summarize_tool_result(tool_result)
            used_tool_this_turn = True
            if tool_result.get("ok") and tool_result.get("tool") in STATE_CHANGING_TOOLS:
                successful_state_change_results.append(tool_result)
            if tool_result.get("ok") and tool_result.get("tool") in DETERMINISTIC_RESULT_TOOLS:
                successful_deterministic_result = tool_result
            if not tool_result.get("ok"):
                last_tool_error_result = tool_result
                if tool_result.get("tool") in STATE_CHANGING_TOOLS:
                    failed_state_change_result = tool_result
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
                    "tool_call_id": tool_call.call_id,
                    "content": json.dumps(tool_result, default=str),
                }
            )
            _ = summarized

        response = provider.submit(
            messages=conversation_messages,
            tools=tools,
            tool_choice=_tool_choice_for_request(require_tool_choice and not used_tool_this_turn),
        )


def summarize_tool_result(tool_result: dict, /) -> str:
    """Create a compact textual summary of a tool result for model context."""
    if tool_result.get("ok"):
        result = tool_result.get("result", {})
        return f"{tool_result['tool']} succeeded: {json.dumps(result, default=str)}"
    error = tool_result.get("error", {})
    return f"{tool_result.get('tool', 'tool')} failed: {error.get('message', 'Unknown error')}"


def _bounded_messages(messages: list[dict]) -> list[dict]:
    history = [message for message in messages if message.get("role") != "system"]
    return history[-MAX_HISTORY_MESSAGES:]


def _assistant_message_from_response(response: NormalizedAssistantTurn) -> dict[str, Any] | None:
    if not response.text and not response.tool_calls:
        return None

    assistant_message: dict[str, Any] = {"role": "assistant", "content": response.text or ""}
    if response.tool_calls:
        assistant_message["tool_calls"] = [
            {
                "id": tool_call.call_id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments),
                },
            }
            for tool_call in response.tool_calls
        ]
    return assistant_message


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
            "This request is a state-changing action. Your very next response must be a tool call if the request is actionable. "
            "Do not ask for confirmation, do not invent dates or IDs, and do not answer with plain text only. "
            "If you need clarification, use lookup tools first when possible and ask only for the missing discriminator. "
            f"Original user request: {user_text}"
        ),
    }


def _tool_choice_for_request(require_tool_choice: bool) -> str | None:
    if require_tool_choice:
        return "required"
    return None


def _render_state_change_clarification(final_text: str) -> str:
    if "?" in final_text:
        return render_clarification(final_text)
    return final_text.strip()


def _render_tool_error(tool_result: dict[str, Any]) -> str:
    error = tool_result.get("error", {})
    message = str(error.get("message", "Unknown tool error")).strip()
    if "?" in message:
        return render_clarification(message)
    return message
