"""Receipt-like terminal renderers."""

from __future__ import annotations

from decimal import Decimal

from retail_agent.types import PurchaseOrderResult, ReturnResult, SaleResult


def render_receipt(result: SaleResult) -> str:
    """Render a deterministic sale receipt view."""
    lines = [
        f"Sale {result.order_id}",
        f"Date: {result.order_date.isoformat()}",
        f"Payment: {result.payment_method}",
        f"Customer: {result.customer_name or result.customer_id or 'Walk-in'}",
    ]
    receipt = result.receipt
    if receipt and receipt.lines:
        lines.append("Items:")
        for line in receipt.lines:
            variant = _variant_text(line.color, line.size)
            lines.append(
                f"- {line.product_name}{variant} x{line.quantity} @ {_format_money(line.paid_unit_price)} = {_format_money(line.paid_unit_price * line.quantity)}"
            )
    lines.extend(
        [
            f"Subtotal: {_format_money(result.subtotal)}",
            f"Discount: {_format_money(result.total_discount)}",
            f"Total: {_format_money(result.total_paid)}",
        ]
    )
    return "\n".join(lines)


def render_return_confirmation(result: ReturnResult) -> str:
    """Render a deterministic return confirmation."""
    lines = [
        f"Return {result.return_id}",
        f"Order: {result.order_id}",
        f"Date: {result.return_date.isoformat()}",
        f"SKU: {result.sku}",
        f"Quantity: {result.quantity}",
        f"Condition: {result.condition}",
        f"Refund: {_format_money(result.refund_amount)}",
        f"Restocked: {result.restocked_quantity}",
    ]
    return "\n".join(lines)


def render_purchase_order(result: PurchaseOrderResult) -> str:
    """Render a deterministic purchase-order confirmation."""
    lines = [
        f"Purchase Order {result.purchase_order_id}",
        f"Supplier: {result.supplier_name} ({result.supplier_id})",
        f"Order Date: {result.order_date.isoformat()}",
        f"Status: {result.status}",
        f"Lines: {result.line_count}",
        f"Total Units: {result.total_units}",
    ]
    return "\n".join(lines)


def _format_money(amount: Decimal) -> str:
    return f"${amount:.2f}"


def _variant_text(color: str | None, size: str | None) -> str:
    bits = [bit for bit in (color, size) if bit]
    if not bits:
        return ""
    return f" ({', '.join(bits)})"

