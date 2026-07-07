from __future__ import annotations

import json
from types import SimpleNamespace

from retail_agent.agent.chat_runtime import run_agent_turn


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "previous_response_id" not in kwargs:
            return SimpleNamespace(
                id="resp-1",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="find_customer",
                        arguments=json.dumps({"query": "Sarah Chen"}),
                        call_id="call-1",
                    )
                ],
                output_text=None,
            )
        return SimpleNamespace(
            id="resp-2",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="Found Sarah Chen.")],
                )
            ],
            output_text="Found Sarah Chen.",
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_mocked_model_completes_tool_call_turn_end_to_end(app_context, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )

    text = run_agent_turn("Find Sarah Chen.", "cli", app_context)

    assert text == "Found Sarah Chen."
    memory = app_context.session_state["cli"]["memory"]
    assert memory.last_customer_id == "C-001"
    assert len(fake_client.responses.calls) == 2
