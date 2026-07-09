"""Deterministic renderers for successful tool payloads."""

from __future__ import annotations

from typing import Any

from retail_agent.presenters.messages import render_success_summary


STATE_CHANGING_TOOLS = {
    "ring_up_sale",
    "process_return",
    "reorder_low_stock",
    "receive_purchase_order",
    "create_promotion",
}

DETERMINISTIC_RESULT_TOOLS = STATE_CHANGING_TOOLS | {
    "top_products_by_margin",
    "stockout_risk_report",
}


def render_state_change_result(tool_result: dict[str, Any]) -> str:
    """Render a successful state-changing tool result from its payload."""
    return render_tool_result(tool_result)


def render_tool_result(tool_result: dict[str, Any]) -> str:
    """Render a successful tool result from its payload when deterministic output is preferred."""
    tool_name = str(tool_result.get("tool", ""))
    payload = tool_result.get("result", {})
    if not isinstance(payload, dict):
        return str(payload)

    if tool_name == "ring_up_sale":
        return _render_sale_payload(payload)
    if tool_name == "process_return":
        return _render_return_payload(payload)
    if tool_name == "receive_purchase_order":
        return _render_purchase_order_payload(payload)
    if tool_name == "reorder_low_stock":
        return _render_reorder_payload(payload)
    if tool_name == "create_promotion":
        return _render_promotion_payload(payload)
    if tool_name == "top_products_by_margin":
        return _render_margin_payload(payload)
    if tool_name == "stockout_risk_report":
        return _render_stockout_payload(payload)
    return render_success_summary(payload)


def _render_sale_payload(payload: dict[str, Any]) -> str:
    customer = payload.get("customer_name") or payload.get("customer_id") or "Walk-in"
    lines = [
        f"**Sale {payload.get('order_id')}**",
        f"- **Date:** {payload.get('order_date')}",
        f"- **Payment:** {payload.get('payment_method')}",
        f"- **Customer:** {customer}",
    ]
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        raw_lines = receipt.get("lines") or []
        if raw_lines:
            lines.append("")
            lines.append("**Items**")
            for line in raw_lines:
                if not isinstance(line, dict):
                    continue
                variant = _variant_text(line.get("color"), line.get("size"))
                lines.append(
                    f"- {line.get('product_name')}{variant} x{line.get('quantity')} at {_format_money(line.get('paid_unit_price'))} each = {_format_money(_line_total(line))}"
                )
    lines.extend(
        [
            "",
            f"- **Subtotal:** {_format_money(payload.get('subtotal'))}",
            f"- **Discount:** {_format_money(payload.get('total_discount'))}",
            f"- **Total:** {_format_money(payload.get('total_paid'))}",
        ]
    )
    return "\n".join(lines)


def _render_return_payload(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"**Return {payload.get('return_id')}**",
            f"- **Order:** {payload.get('order_id')}",
            f"- **Date:** {payload.get('return_date')}",
            f"- **SKU:** {payload.get('sku')}",
            f"- **Quantity:** {payload.get('quantity')}",
            f"- **Condition:** {payload.get('condition')}",
            f"- **Refund:** {_format_money(payload.get('refund_amount'))}",
            f"- **Restocked:** {payload.get('restocked_quantity')}",
        ]
    )


def _render_purchase_order_payload(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"**Purchase Order {payload.get('purchase_order_id')}**",
            f"- **Supplier:** {payload.get('supplier_name')} ({payload.get('supplier_id')})",
            f"- **Order Date:** {payload.get('order_date')}",
            f"- **Status:** {payload.get('status')}",
            f"- **Lines:** {payload.get('line_count')}",
            f"- **Total Units:** {payload.get('total_units')}",
        ]
    )


def _render_reorder_payload(payload: dict[str, Any]) -> str:
    purchase_orders = payload.get("purchase_orders") or []
    count = payload.get("count", len(purchase_orders))
    if not purchase_orders:
        return f"**Reorder Complete**\n\n- **Created:** {count} purchase orders"
    lines = [f"**Reorder Complete**", "", f"- **Created:** {count} purchase orders"]
    for purchase_order in purchase_orders:
        if not isinstance(purchase_order, dict):
            continue
        lines.append(
            f"- {purchase_order.get('purchase_order_id')}: {purchase_order.get('supplier_name')} ({purchase_order.get('status')}), {purchase_order.get('total_units')} units"
        )
    return "\n".join(lines)


def _render_promotion_payload(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"**Promotion {payload.get('promo_id')}**",
            f"- **Description:** {payload.get('description')}",
            f"- **Scope:** {payload.get('scope_type')}={payload.get('scope_ref')}",
            f"- **Percent Off:** {payload.get('percent_off')}%",
            f"- **Dates:** {payload.get('start_date')} to {payload.get('end_date')}",
        ]
    )


def _render_margin_payload(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    if not rows:
        return "**Top Products By Profit Margin**\n\nNo margin rows found."

    lines = ["**Top Products By Profit Margin**", ""]
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        margin_pct = _format_margin_percent(row.get("margin"), row.get("revenue"))
        lines.append(
            f"{index}. {row.get('product_name')} ({row.get('product_id')}): "
            f"{_format_money(row.get('margin'))} margin on {_format_money(row.get('revenue'))} revenue"
            + (f" [{margin_pct}]" if margin_pct is not None else "")
        )
    return "\n".join(lines)


def _render_stockout_payload(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    if not rows:
        return "**Stockout Risk Report**\n\nNo stockout risks found."

    lines = ["**Stockout Risk Report**", ""]
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- {row.get('product_name')} ({row.get('product_id')}): "
            f"on hand {row.get('on_hand_qty')}, reorder point {row.get('reorder_point')}, "
            f"monthly units {row.get('monthly_units')}, days of cover {_format_days_cover(row.get('days_of_cover'))}"
        )
        reason = row.get("reason")
        if reason:
            lines.append(f"  Reason: {reason}")
    return "\n".join(lines)


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _line_total(line: dict[str, Any]) -> float:
    try:
        return float(line.get("paid_unit_price", 0)) * float(line.get("quantity", 0))
    except (TypeError, ValueError):
        return 0.0


def _variant_text(color: Any, size: Any) -> str:
    bits = [str(bit) for bit in (color, size) if bit]
    if not bits:
        return ""
    return f" ({', '.join(bits)})"


def _format_days_cover(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "n/a"


def _format_margin_percent(margin: Any, revenue: Any) -> str | None:
    try:
        revenue_value = float(revenue)
        if revenue_value == 0:
            return None
        margin_value = float(margin)
        return f"{(margin_value / revenue_value) * 100:.0f}% margin"
    except (TypeError, ValueError, ZeroDivisionError):
        return None
