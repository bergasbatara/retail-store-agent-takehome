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


def test_missing_tool_arguments_return_friendly_validation_error(app_context):
    result = execute_tool_call("find_product", {}, app_context)

    assert result["ok"] is False
    assert result["error"]["type"] == "ValidationError"
    assert result["error"]["message"] == "Need clarification: which product should I look up?"


def test_find_order_and_purchase_order_lookup_tools_return_structured_matches(app_context):
    order_result = execute_tool_call("find_order", {"query": "O-1006"}, app_context)
    reorder_result = execute_tool_call("reorder_low_stock", {"order_date": "2026-06-19"}, app_context)
    po_id = reorder_result["result"]["purchase_orders"][0]["purchase_order_id"]
    po_result = execute_tool_call("find_purchase_order", {"query": po_id}, app_context)

    assert order_result["ok"] is True
    assert order_result["result"]["order"]["order"]["order_id"] == "O-1006"
    assert po_result["ok"] is True
    assert po_result["result"]["purchase_order"]["purchase_order"]["purchase_order_id"] == po_id


def test_product_price_can_resolve_from_query_and_variant(app_context):
    result = execute_tool_call(
        "get_product_price",
        {
            "query": "hoodie",
            "color": "Gray",
            "size": "Medium",
            "sale_date": "2026-06-21",
        },
        app_context,
    )

    assert result["ok"] is True
    assert result["result"]["sku"] == "HOOD-GRY-M"


def test_receive_purchase_order_can_resolve_product_name_to_po_line(app_context):
    reorder_result = execute_tool_call("reorder_low_stock", {"order_date": "2026-06-19"}, app_context)
    po_id = reorder_result["result"]["purchase_orders"][0]["purchase_order_id"]

    receive_result = execute_tool_call(
        "receive_purchase_order",
        {
            "purchase_order_id": po_id,
            "receive_date": "2026-06-19",
            "received_items": [{"product_name": "Canvas Tote", "quantity_received": 40}],
        },
        app_context,
    )

    assert receive_result["ok"] is True
    assert receive_result["result"]["purchase_order_id"] == po_id
