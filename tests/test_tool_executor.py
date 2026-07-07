from __future__ import annotations

from retail_agent.agent.tool_executor import execute_tool_call


def test_tool_arguments_are_validated_and_dispatched(app_context):
    success = execute_tool_call(
        "get_product_price",
        {"sku": "TEE-BLU-M", "sale_date": "2026-05-02"},
        app_context,
    )
    failure = execute_tool_call(
        "ring_up_sale",
        {
            "payment_method": "cash",
            "order_date": "2026-06-19",
            "items": [{"product_name": "Pullover Hoodie", "quantity": 1, "size": "M"}],
        },
        app_context,
    )

    assert success["ok"] is True
    assert success["result"]["effective_unit_price"] == "20.00"
    assert failure["ok"] is False
    assert failure["error"]["type"] == "AmbiguityError"

