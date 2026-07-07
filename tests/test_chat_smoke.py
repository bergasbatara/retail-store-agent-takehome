from __future__ import annotations

import json
from types import SimpleNamespace

from retail_agent.agent.chat_runtime import run_agent_turn


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="find_customer",
                                        arguments=json.dumps({"query": "Sarah Chen"}),
                                    ),
                                )
                            ],
                        )
                    )
                ],
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Found Sarah Chen.",
                        tool_calls=[],
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


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
    assert len(fake_client.chat.completions.calls) == 2
