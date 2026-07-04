"""Report-oriented terminal renderers."""

from __future__ import annotations

from decimal import Decimal

from retail_agent.types import MarginReportRow, StockoutAlert


def render_margin_report(rows: list[MarginReportRow]) -> str:
    """Render a deterministic product-margin report."""
    if not rows:
        return "No margin rows found."

    header = "Product | Units | Revenue | Cost | Margin"
    body = [
        (
            f"{row.product_name} ({row.product_id}) | "
            f"{row.units_sold} | "
            f"{_format_money(row.revenue)} | "
            f"{_format_money(row.cost)} | "
            f"{_format_money(row.margin)}"
        )
        for row in rows
    ]
    return "\n".join([header, *body])


def render_stockout_report(rows: list[StockoutAlert]) -> str:
    """Render a deterministic stock-out risk report."""
    if not rows:
        return "No stockout risks found."

    header = "Product | On Hand | Reorder Point | Monthly Units | Days Cover | Reason"
    body = [
        (
            f"{row.product_name} ({row.product_id}) | "
            f"{row.on_hand_qty} | "
            f"{row.reorder_point} | "
            f"{row.monthly_units} | "
            f"{_format_days_cover(row.days_of_cover)} | "
            f"{row.reason}"
        )
        for row in rows
    ]
    return "\n".join([header, *body])


def _format_money(amount: Decimal) -> str:
    return f"${amount:.2f}"


def _format_days_cover(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"

