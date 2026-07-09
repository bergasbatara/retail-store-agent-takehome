from __future__ import annotations

from retail_agent.agent.policy import (
    contains_fake_operational_payload,
    contains_pseudo_tool_markup,
    response_satisfies_policy,
)


def test_pseudo_tool_markup_detection_handles_malformed_marker_text():
    text = "Hakutfunction<| tool_sep |>find_product\n```json\n{\"query\": \"hoodie\"}\n```<| tool_call_end |>"

    assert contains_pseudo_tool_markup(text) is True


def test_state_changing_plaintext_with_pseudo_tool_markup_fails_policy():
    text = "<|tool_calls_begin|><|tool_call_begin|>function<|tool_sep|>find_product"

    assert response_satisfies_policy(
        "Ring up a hoodie for Sarah Chen.",
        [],
        text,
    ) is False


def test_xml_style_fake_tool_call_markup_fails_policy():
    text = """<tool_call>
{"name": "create_sale", "arguments": {"customer_id": "C-WALKIN", "sale_date": "2026-07-08"}}
</tool_call>"""

    assert contains_pseudo_tool_markup(text) is True
    assert response_satisfies_policy(
        "Ring up two Classic Tees and one Canvas Tote for a walk-in.",
        [],
        text,
    ) is False


def test_clarification_mixed_with_fake_receipt_fails_policy():
    text = """Could you confirm the hoodie color?

**Sale O-1021**
- **Date:** 2026-07-08
- **Customer:** Sarah Chen (C-001)
- **Payment:** cash
"""

    assert contains_fake_operational_payload(text) is True
    assert response_satisfies_policy(
        "Ring up a hoodie in medium for Sarah Chen.",
        [],
        text,
    ) is False
