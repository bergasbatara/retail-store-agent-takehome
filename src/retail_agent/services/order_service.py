"""Order and checkout workflow coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import (
    CatalogRepository,
    CustomerRepository,
    InventoryRepository,
    OrderRepository,
    PromotionRepository,
)
from retail_agent.domain.customers import resolve_customer
from retail_agent.domain.resolution import resolve_sale_items
from retail_agent.ids import next_order_id
from retail_agent.money import quantize_cents, to_decimal
from retail_agent.services.inventory_service import assert_inventory_available
from retail_agent.services.pricing_service import PricingRepositories, price_sale_items
from retail_agent.types import (
    OrderLineDraft,
    PricedLine,
    ReceiptView,
    SaleItemInput,
    SaleResult,
)


ZERO_DECIMAL = Decimal("0.00")


@dataclass(frozen=True)
class OrderRepositories:
    """Repository bundle used by checkout operations."""

    catalog: CatalogRepository
    customers: CustomerRepository
    inventory: InventoryRepository
    orders: OrderRepository
    promotions: PromotionRepository


def create_sale(
    customer_ref: str | None,
    items: list[SaleItemInput],
    payment_method: str,
    order_date: date,
    repos: OrderRepositories,
    *,
    order_discount_pct: Decimal = ZERO_DECIMAL,
) -> SaleResult:
    """Create a customer-linked sale and persist it atomically."""
    customer = resolve_customer(customer_ref, repos.customers)
    return _create_sale(
        customer_id=customer.customer_id if customer else None,
        customer_name=customer.name if customer else None,
        items=items,
        payment_method=payment_method,
        order_date=order_date,
        repos=repos,
        order_discount_pct=order_discount_pct,
    )


def create_walk_in_sale(
    items: list[SaleItemInput],
    payment_method: str,
    order_date: date,
    repos: OrderRepositories,
    *,
    order_discount_pct: Decimal = ZERO_DECIMAL,
) -> SaleResult:
    """Create a walk-in sale and persist it atomically."""
    return _create_sale(
        customer_id=None,
        customer_name=None,
        items=items,
        payment_method=payment_method,
        order_date=order_date,
        repos=repos,
        order_discount_pct=order_discount_pct,
    )


def build_order_lines(priced_items: list[PricedLine]) -> list[OrderLineDraft]:
    """Convert priced items into persisted order-line drafts."""
    return [
        OrderLineDraft(
            line_no=index,
            sku=item.sku,
            quantity=item.quantity,
            unit_price=item.effective_unit_price,
            paid_unit_price=item.paid_unit_price,
            product_id=item.product_id,
            product_name=item.product_name,
            color=item.color,
            size=item.size,
            applied_promotion=item.applied_promotion,
        )
        for index, item in enumerate(priced_items, start=1)
    ]


def persist_sale(
    order_draft: ReceiptView,
    repos: OrderRepositories,
) -> str:
    """Persist an order header and its lines in a single transaction."""
    conn = repos.orders.conn
    with conn:
        repos.orders.create_order(
            order_id=order_draft.order_id,
            order_date=order_draft.order_date.isoformat(),
            customer_id=order_draft.customer_id,
            order_discount_pct=str(order_draft.total_discount and _discount_pct_from_receipt(order_draft) or Decimal("0")),
            payment_method=order_draft.payment_method,
            commit=False,
        )
        for line in order_draft.lines:
            repos.orders.add_order_line(
                order_id=order_draft.order_id,
                line_no=line.line_no,
                sku=line.sku,
                quantity=line.quantity,
                unit_price=str(line.unit_price),
                commit=False,
            )
    return order_draft.order_id


def format_receipt_data(order_id: str, repos: OrderRepositories) -> ReceiptView:
    """Load a persisted order into a receipt-oriented projection."""
    bundle = repos.orders.get_order_with_lines(order_id)
    if bundle is None:
        raise ValueError(f"Order '{order_id}' was not found.")

    order = bundle["order"]
    customer_name = None
    if order["customer_id"] is not None:
        customer = repos.customers.get_customer(order["customer_id"])
        customer_name = customer["name"] if customer is not None else None

    lines = tuple(
        OrderLineDraft(
            line_no=int(line["line_no"]),
            sku=line["sku"],
            quantity=int(line["quantity"]),
            unit_price=to_decimal(line["unit_price"]),
            paid_unit_price=quantize_cents(
                to_decimal(line["unit_price"])
                * (Decimal("1") - (to_decimal(order["order_discount_pct"]) / Decimal("100")))
            ),
            product_id=line["product_id"],
            product_name=line["product_name"],
            color=line.get("color"),
            size=line.get("size"),
            applied_promotion=None,
        )
        for line in bundle["lines"]
    )
    subtotal = quantize_cents(sum((line.unit_price * line.quantity for line in lines), Decimal("0")))
    total_paid = quantize_cents(sum((line.paid_unit_price * line.quantity for line in lines), Decimal("0")))
    total_discount = quantize_cents(subtotal - total_paid)
    return ReceiptView(
        order_id=order["order_id"],
        order_date=date.fromisoformat(order["order_date"]),
        payment_method=order["payment_method"],
        customer_id=order["customer_id"],
        customer_name=customer_name,
        subtotal=subtotal,
        total_discount=total_discount,
        total_paid=total_paid,
        lines=lines,
    )


def _create_sale(
    *,
    customer_id: str | None,
    customer_name: str | None,
    items: list[SaleItemInput],
    payment_method: str,
    order_date: date,
    repos: OrderRepositories,
    order_discount_pct: Decimal,
) -> SaleResult:
    resolved_items = resolve_sale_items(items, repos.catalog)
    for item in resolved_items:
        assert_inventory_available(item.sku, item.quantity, repos.inventory)

    priced_items = price_sale_items(
        resolved_items,
        order_date,
        order_discount_pct,
        PricingRepositories(catalog=repos.catalog, promotions=repos.promotions),
    )
    order_lines = build_order_lines(priced_items)

    order_id = next_order_id(repos.orders.conn)
    receipt = ReceiptView(
        order_id=order_id,
        order_date=order_date,
        payment_method=payment_method,
        customer_id=customer_id,
        customer_name=customer_name,
        subtotal=_compute_subtotal(order_lines),
        total_discount=_compute_total_discount(order_lines),
        total_paid=_compute_total_paid(order_lines),
        lines=tuple(order_lines),
    )

    _persist_sale_with_inventory(
        order_draft=receipt,
        resolved_items=resolved_items,
        order_discount_pct=order_discount_pct,
        repos=repos,
    )
    return SaleResult(
        order_id=receipt.order_id,
        order_date=receipt.order_date,
        payment_method=receipt.payment_method,
        customer_id=receipt.customer_id,
        customer_name=receipt.customer_name,
        subtotal=receipt.subtotal,
        total_discount=receipt.total_discount,
        total_paid=receipt.total_paid,
        receipt=receipt,
        line_items=receipt.lines,
        message=f"Created sale {receipt.order_id}.",
    )


def _persist_sale_with_inventory(
    *,
    order_draft: ReceiptView,
    resolved_items: list,
    order_discount_pct: Decimal,
    repos: OrderRepositories,
) -> None:
    conn = repos.orders.conn
    with conn:
        repos.orders.create_order(
            order_id=order_draft.order_id,
            order_date=order_draft.order_date.isoformat(),
            customer_id=order_draft.customer_id,
            order_discount_pct=str(order_discount_pct),
            payment_method=order_draft.payment_method,
            commit=False,
        )
        for line in order_draft.lines:
            repos.orders.add_order_line(
                order_id=order_draft.order_id,
                line_no=line.line_no,
                sku=line.sku,
                quantity=line.quantity,
                unit_price=str(line.unit_price),
                commit=False,
            )
        for item in resolved_items:
            repos.inventory.adjust_on_hand(item.sku, -item.quantity, commit=False)


def _compute_subtotal(lines: list[OrderLineDraft]) -> Decimal:
    return quantize_cents(sum((line.unit_price * line.quantity for line in lines), Decimal("0")))


def _compute_total_paid(lines: list[OrderLineDraft]) -> Decimal:
    return quantize_cents(sum((line.paid_unit_price * line.quantity for line in lines), Decimal("0")))


def _compute_total_discount(lines: list[OrderLineDraft]) -> Decimal:
    return quantize_cents(_compute_subtotal(lines) - _compute_total_paid(lines))


def _discount_pct_from_receipt(order_draft: ReceiptView) -> Decimal:
    if order_draft.subtotal == Decimal("0"):
        return Decimal("0")
    return quantize_cents((order_draft.total_discount / order_draft.subtotal) * Decimal("100"))
