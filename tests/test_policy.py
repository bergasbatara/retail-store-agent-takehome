from __future__ import annotations

from retail_agent.agent.policy import contains_pseudo_tool_markup, response_satisfies_policy


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
