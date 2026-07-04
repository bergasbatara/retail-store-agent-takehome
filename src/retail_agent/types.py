"""Shared domain-facing dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SaleItemInput:
    """User-requested sale line before catalog resolution."""

    product_name: str
    quantity: int
    sku: str | None = None
    color: str | None = None
    size: str | None = None


@dataclass(frozen=True)
class ResolvedSku:
    """Concrete sellable unit after resolution."""

    sku: str
    product_id: str
    product_name: str
    quantity: int
    category: str
    color: str | None = None
    size: str | None = None
    retail_price: Decimal | None = None


@dataclass(frozen=True)
class SaleResult:
    """Persisted sale result returned by checkout flows."""

    order_id: str
    order_date: date
    payment_method: str
    customer_id: str | None
    customer_name: str | None
    subtotal: Decimal
    total_discount: Decimal
    total_paid: Decimal
    line_items: tuple[ResolvedSku, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class ReturnResult:
    """Persisted return result."""

    return_id: str
    order_id: str
    return_date: date
    sku: str
    quantity: int
    condition: str
    refund_amount: Decimal
    restocked_quantity: int
    message: str = ""


@dataclass(frozen=True)
class PurchaseOrderResult:
    """Purchase order creation or receiving result."""

    purchase_order_id: str
    supplier_id: str
    supplier_name: str
    order_date: date
    status: str
    line_count: int
    total_units: int
    message: str = ""


@dataclass(frozen=True)
class StockoutAlert:
    """Stock-out risk result for one product."""

    product_id: str
    product_name: str
    on_hand_qty: int
    reorder_point: int
    monthly_units: int
    days_of_cover: Decimal | None
    below_reorder_point: bool
    low_days_of_cover: bool
    reason: str = ""


@dataclass(frozen=True)
class MarginReportRow:
    """Margin report row for one product."""

    product_id: str
    product_name: str
    units_sold: int
    revenue: Decimal
    cost: Decimal
    margin: Decimal
