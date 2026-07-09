from __future__ import annotations

from retail_agent.presenters.messages import render_success_summary
from retail_agent.presenters.tool_results import render_state_change_result, render_tool_result


def test_sale_tool_result_renders_markdown_friendly_receipt():
    tool_result = {
        "ok": True,
        "tool": "ring_up_sale",
        "result": {
            "order_id": "O-1017",
            "order_date": "2026-07-07",
            "payment_method": "cash",
            "customer_name": None,
            "subtotal": "68.00",
            "total_discount": "0.00",
            "total_paid": "68.00",
            "receipt": {
                "lines": [
                    {
                        "product_name": "Classic Tee",
                        "color": "Blue",
                        "size": "M",
                        "quantity": 2,
                        "paid_unit_price": "25.00",
                    },
                    {
                        "product_name": "Canvas Tote",
                        "color": None,
                        "size": None,
                        "quantity": 1,
                        "paid_unit_price": "18.00",
                    },
                ]
            },
        },
    }

    text = render_state_change_result(tool_result)

    assert "**Sale O-1017**" in text
    assert "**Items**" in text
    assert "- **Total:** $68.00" in text
    assert "Classic Tee (Blue, M) x2 at $25.00 each = $50.00" in text


def test_success_summary_renders_bulleted_markdown():
    text = render_success_summary({"count": 2, "status": "ok"})

    assert text.startswith("**Success**")
    assert "- **Count:** 2" in text
    assert "- **Status:** ok" in text


def test_margin_tool_result_renders_deterministically():
    tool_result = {
        "ok": True,
        "tool": "top_products_by_margin",
        "result": {
            "rows": [
                {
                    "product_id": "P-HOOD",
                    "product_name": "Pullover Hoodie",
                    "units_sold": 8,
                    "revenue": "480.00",
                    "cost": "224.00",
                    "margin": "256.00",
                }
            ],
            "count": 1,
        },
    }

    text = render_tool_result(tool_result)

    assert text.startswith("**Top Products By Profit Margin**")
    assert "Pullover Hoodie (P-HOOD): $256.00 margin on $480.00 revenue" in text
    assert "53% margin" in text


def test_stockout_tool_result_renders_deterministically():
    tool_result = {
        "ok": True,
        "tool": "stockout_risk_report",
        "result": {
            "rows": [
                {
                    "product_id": "P-TOTE",
                    "product_name": "Canvas Tote",
                    "on_hand_qty": 4,
                    "reorder_point": 10,
                    "monthly_units": 9,
                    "days_of_cover": "13.3",
                    "reason": "Below reorder point and under 14 days of cover",
                }
            ],
            "count": 1,
        },
    }

    text = render_tool_result(tool_result)

    assert text.startswith("**Stockout Risk Report**")
    assert "Canvas Tote (P-TOTE): on hand 4, reorder point 10" in text
    assert "Reason: Below reorder point and under 14 days of cover" in text
