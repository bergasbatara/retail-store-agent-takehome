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
class ProductResolution:
    """Resolved product reference with candidate SKU matches."""

    query: str
    product_name: str
    product_id: str
    candidates: tuple[ResolvedSku, ...]


@dataclass(frozen=True)
class Customer:
    """Resolved customer record."""

    customer_id: str
    name: str
    email: str
    joined_date: date


@dataclass(frozen=True)
class ResolvedReturnItem:
    """Concrete return target resolved from an order reference."""

    order_id: str
    sku: str
    product_id: str
    product_name: str
    quantity_purchased: int
    color: str | None = None
    size: str | None = None


@dataclass(frozen=True)
class Promotion:
    """Normalized promotion record used by pricing logic."""

    promo_id: str
    description: str
    type: str
    value: Decimal
    scope_type: str
    scope_ref: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class PricedLine:
    """Resolved sale line with pricing details applied."""

    sku: str
    product_id: str
    product_name: str
    quantity: int
    category: str
    color: str | None
    size: str | None
    base_unit_price: Decimal
    effective_unit_price: Decimal
    paid_unit_price: Decimal
    applied_promotion: Promotion | None = None


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


@dataclass(frozen=True)
class SeedDataBundle:
    """Normalized seed data loaded from the CSV exports."""

    products: tuple[dict, ...]
    customers: tuple[dict, ...]
    suppliers: tuple[dict, ...]
    supplier_catalog: tuple[dict, ...]
    inventory: tuple[dict, ...]
    orders: tuple[dict, ...]
    order_lines: tuple[dict, ...]
    returns: tuple[dict, ...]
    promotions: tuple[dict, ...]
