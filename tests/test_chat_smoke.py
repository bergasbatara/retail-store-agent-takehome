from __future__ import annotations

import json
from types import SimpleNamespace

from retail_agent.agent.chat_runtime import run_agent_turn
from retail_agent.session.memory import SessionMemory


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


class RetryFakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="I will process the sale today (2023-11-15).",
                            tool_calls=[],
                        )
                    )
                ],
            )
        if len(self.calls) == 2:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-2",
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
                        content="Found Sarah Chen after retry.",
                        tool_calls=[],
                    )
                )
            ]
        )


class RetryFakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=RetryFakeCompletions())


def test_state_changing_plaintext_response_is_reprompted(app_context, monkeypatch):
    fake_client = RetryFakeClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )

    text = run_agent_turn("Ring up ten Canvas Totes for a walk-in.", "cli", app_context)

    assert text == "Found Sarah Chen after retry."
    assert len(fake_client.chat.completions.calls) == 3
    retry_messages = fake_client.chat.completions.calls[1]["messages"]
    assert any(
        message.get("role") == "system"
        and "requires tool use" in message.get("content", "")
        for message in retry_messages
        if isinstance(message, dict)
    )


class PseudoToolTextCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='<tool_call>\n{"name": "create_sale", "arguments": {"payment_method": "cash"}}\n</tool_call>',
                        tool_calls=[],
                    )
                )
            ],
        )


class PseudoToolTextClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=PseudoToolTextCompletions())


def test_state_changing_pseudo_tool_text_does_not_fall_back_to_empty_response(app_context, monkeypatch):
    fake_client = PseudoToolTextClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )

    text = run_agent_turn(
        "Ring up two Classic Tees, Blue Medium, and one Canvas Tote for a walk-in paying cash, dated today.",
        "cli",
        app_context,
    )

    assert text != "No response was produced."
    assert "required tool" in text


class FlexibleXmlToolCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='<tool_call>\n{"name": "find_customer", "arguments": {"query": "Sarah Chen"}}\n</tool_call>',
                            tool_calls=[],
                        )
                    )
                ],
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Found Sarah Chen via normalized provider call.",
                        tool_calls=[],
                    )
                )
            ]
        )


class FlexibleXmlToolClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FlexibleXmlToolCompletions())


def test_xml_style_tool_markup_can_be_safely_normalized_when_schema_matches(app_context, monkeypatch):
    fake_client = FlexibleXmlToolClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )

    text = run_agent_turn("Find Sarah Chen.", "cli", app_context)

    assert text == "Found Sarah Chen via normalized provider call."


class VariantFollowUpCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Clarified against prior candidates.",
                        tool_calls=[],
                    )
                )
            ],
        )


class VariantFollowUpClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=VariantFollowUpCompletions())


def test_variant_only_follow_up_injects_candidate_bound_hint(app_context, monkeypatch):
    fake_client = VariantFollowUpClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )
    app_context.session_state["cli"] = {
        "messages": [],
        "tool_results": [],
        "memory": SessionMemory(last_product_candidates=("HOOD-GRY-M", "HOOD-NVY-M")),
    }

    text = run_agent_turn("Gray", "cli", app_context)

    assert text == "Clarified against prior candidates."
    messages = fake_client.chat.completions.calls[0]["messages"]
    assert any(
        message.get("role") == "system"
        and "recent candidate SKUs" in message.get("content", "")
        and "HOOD-GRY-M" in message.get("content", "")
        for message in messages
        if isinstance(message, dict)
    )


class VariantFollowUpRetryCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="Use SKU HOOD-NAV-M for the sale.",
                            tool_calls=[],
                        )
                    )
                ],
            )
        if len(self.calls) == 2:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-variant-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="find_product",
                                        arguments=json.dumps(
                                            {"query": "Pullover Hoodie", "color": "Navy", "size": "M"}
                                        ),
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
                        content="Found the exact hoodie variant.",
                        tool_calls=[],
                    )
                )
            ]
        )


class VariantFollowUpRetryClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=VariantFollowUpRetryCompletions())


def test_variant_follow_up_inherits_previous_sale_intent_and_reprompts(app_context, monkeypatch):
    fake_client = VariantFollowUpRetryClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )
    app_context.session_state["cli"] = {
        "messages": [
            {"role": "user", "content": "Ring up a hoodie in medium for Sarah Chen"},
            {
                "role": "assistant",
                "content": "Need clarification: Multiple Pullover Hoodie variants match. Which color did you want? Options: Gray, Navy.",
            },
        ],
        "tool_results": [],
        "memory": SessionMemory(last_product_candidates=("HOOD-GRY-M", "HOOD-NVY-M")),
    }

    text = run_agent_turn("Navy", "cli", app_context)

    assert text == "Found the exact hoodie variant."
    assert len(fake_client.chat.completions.calls) == 3
    retry_messages = fake_client.chat.completions.calls[1]["messages"]
    assert any(
        message.get("role") == "system"
        and "requires tool use" in message.get("content", "")
        for message in retry_messages
        if isinstance(message, dict)
    )


class WrongToolIntentCompletions:
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
                                    id="call-wrong-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="process_return",
                                        arguments=json.dumps(
                                            {
                                                "order_id": "O-1006",
                                                "sku_or_ref": "TOTE",
                                                "quantity": 1,
                                                "condition": "damaged",
                                                "return_date": "2026-07-09",
                                            }
                                        ),
                                    ),
                                )
                            ],
                        )
                    )
                ],
            )
        if len(self.calls) == 2:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-right-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="stockout_risk_report",
                                        arguments=json.dumps({"as_of_date": "2026-07-09"}),
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
                        content="Here is the stockout report.",
                        tool_calls=[],
                    )
                )
            ]
        )


class WrongToolIntentClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=WrongToolIntentCompletions())


def test_wrong_tool_intent_is_rejected_and_retried(app_context, monkeypatch):
    fake_client = WrongToolIntentClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.execute_tool_call",
        lambda name, arguments, app_context: {
            "ok": True,
            "tool": name,
            "result": {"rows": [], "count": 0},
        },
    )

    text = run_agent_turn("What's about to stock out?", "cli", app_context)

    assert "Stockout Risk Report" in text
    assert len(fake_client.chat.completions.calls) == 3
    retry_messages = fake_client.chat.completions.calls[1]["messages"]
    assert any(
        message.get("role") == "system"
        and "did not match the request intent" in message.get("content", "")
        for message in retry_messages
        if isinstance(message, dict)
    )


class ReturnLookupFirstCompletions:
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
                                    id="call-return-wrong",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="process_return",
                                        arguments=json.dumps(
                                            {
                                                "order_id": "O-1006",
                                                "sku_or_ref": "TOTE-CNV-S",
                                                "quantity": 1,
                                                "condition": "damaged",
                                                "return_date": "2026-07-09",
                                            }
                                        ),
                                    ),
                                )
                            ],
                        )
                    )
                ],
            )
        if len(self.calls) == 2:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-return-right",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="find_order",
                                        arguments=json.dumps({"query": "O-1006"}),
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
                        content="Need clarification: which item on the order should I return?",
                        tool_calls=[],
                    )
                )
            ]
        )


class ReturnLookupFirstClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=ReturnLookupFirstCompletions())


def test_return_flow_requires_find_order_before_process_return(app_context, monkeypatch):
    fake_client = ReturnLookupFirstClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.execute_tool_call",
        lambda name, arguments, app_context: {
            "ok": True,
            "tool": name,
            "result": {"orders": [{"order_id": "O-1006"}], "count": 1},
        },
    )

    text = run_agent_turn("Return the Canvas Tote from order O-1006 — it came back damaged.", "cli", app_context)

    assert "Need clarification" in text
    retry_messages = fake_client.chat.completions.calls[1]["messages"]
    assert any(
        message.get("role") == "system"
        and "resolve the record first with find_order" in message.get("content", "")
        for message in retry_messages
        if isinstance(message, dict)
    )


class ReceiveLookupFirstCompletions:
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
                                    id="call-receive-wrong",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="receive_purchase_order",
                                        arguments=json.dumps(
                                            {
                                                "purchase_order_id": "PO-0001",
                                                "receive_date": "2026-07-09",
                                                "received_items": [
                                                    {"sku": "TOTE-CNV-S", "quantity_received": 40}
                                                ],
                                            }
                                        ),
                                    ),
                                )
                            ],
                        )
                    )
                ],
            )
        if len(self.calls) == 2:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-receive-right",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="find_purchase_order",
                                        arguments=json.dumps({"query": "Northwind"}),
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
                        content="Need clarification: which purchase order should I receive?",
                        tool_calls=[],
                    )
                )
            ]
        )


class ReceiveLookupFirstClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=ReceiveLookupFirstCompletions())


def test_receive_flow_requires_find_purchase_order_before_receiving(app_context, monkeypatch):
    fake_client = ReceiveLookupFirstClient()
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.build_openai_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        "retail_agent.agent.chat_runtime.execute_tool_call",
        lambda name, arguments, app_context: {
            "ok": True,
            "tool": name,
            "result": {"purchase_orders": [{"purchase_order_id": "PO-0001"}], "count": 1},
        },
    )

    text = run_agent_turn(
        "A purchase order for 50 Canvas Totes from Northwind is open and 40 arrived — receive them, dated today.",
        "cli",
        app_context,
    )

    assert "Need clarification" in text
    retry_messages = fake_client.chat.completions.calls[1]["messages"]
    assert any(
        message.get("role") == "system"
        and "resolve the record first with find_purchase_order" in message.get("content", "")
        for message in retry_messages
        if isinstance(message, dict)
    )
