"""Procurement and purchase-order receiving workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import (
    CatalogRepository,
    InventoryRepository,
    PurchaseOrderRepository,
    SupplierRepository,
)
from retail_agent.exceptions import NotFoundError, ValidationError
from retail_agent.ids import next_purchase_order_id
from retail_agent.money import to_decimal
from retail_agent.types import (
    PurchaseOrderResult,
    ReceiveItemInput,
    ReorderCandidate,
    SupplierOffer,
)


MAX_ELIGIBLE_LEAD_TIME_DAYS = 10


@dataclass(frozen=True)
class ProcurementRepositories:
    """Repository bundle used by procurement workflows."""

    catalog: CatalogRepository
    inventory: InventoryRepository
    purchase_orders: PurchaseOrderRepository
    suppliers: SupplierRepository


def select_best_supplier(
    product_id: str,
    supplier_repo: SupplierRepository,
) -> SupplierOffer:
    """Select the cheapest supplier that can deliver within 10 days."""
    offers = supplier_repo.list_supplier_offers(product_id)
    eligible = [
        offer
        for offer in offers
        if int(offer["lead_time_days"]) <= MAX_ELIGIBLE_LEAD_TIME_DAYS
    ]
    if not eligible:
        raise NotFoundError(f"No eligible supplier found for product '{product_id}'.")

    best = min(
        eligible,
        key=lambda offer: (to_decimal(offer["unit_cost"]), int(offer["lead_time_days"]), offer["supplier_id"]),
    )
    return SupplierOffer(
        supplier_id=best["supplier_id"],
        supplier_name=best["supplier_name"],
        product_id=best["product_id"],
        unit_cost=to_decimal(best["unit_cost"]),
        lead_time_days=int(best["lead_time_days"]),
    )


def find_reorder_candidates(
    inventory_repo: InventoryRepository,
    catalog_repo: CatalogRepository,
) -> list[ReorderCandidate]:
    """List SKU-level reorder candidates based on inventory thresholds."""
    _ = catalog_repo
    rows = inventory_repo.list_reorder_candidates()
    return [
        ReorderCandidate(
            sku=row["sku"],
            product_id=row["product_id"],
            product_name=row["product_name"],
            quantity_to_order=int(row["reorder_qty"]),
            on_hand_qty=int(row["on_hand_qty"]),
            reorder_point=int(row["reorder_point"]),
            reorder_qty=int(row["reorder_qty"]),
            color=row.get("color"),
            size=row.get("size"),
        )
        for row in rows
    ]


def create_reorder_purchase_orders(
    order_date: date,
    repos: ProcurementRepositories,
) -> list[PurchaseOrderResult]:
    """Create one purchase order per reorder candidate SKU."""
    candidates = find_reorder_candidates(repos.inventory, repos.catalog)
    return [
        create_purchase_order_for_product(
            product_id=candidate.product_id,
            quantity=candidate.quantity_to_order,
            order_date=order_date,
            repos=repos,
            sku=candidate.sku,
        )
        for candidate in candidates
    ]


def create_purchase_order_for_product(
    product_id: str,
    quantity: int,
    order_date: date,
    repos: ProcurementRepositories,
    *,
    sku: str | None = None,
) -> PurchaseOrderResult:
    """Create a purchase order for a product, optionally targeting a specific SKU."""
    if quantity <= 0:
        raise ValidationError("Purchase order quantity must be greater than zero.")

    supplier_offer = select_best_supplier(product_id, repos.suppliers)
    target_sku = sku or _default_sku_for_product(product_id, repos.catalog)
    sku_row = repos.catalog.get_sku(target_sku)
    if sku_row is None:
        raise NotFoundError(f"SKU '{target_sku}' was not found for product '{product_id}'.")

    purchase_order_id = next_purchase_order_id(repos.purchase_orders.conn)
    conn = repos.purchase_orders.conn
    with conn:
        repos.purchase_orders.create_purchase_order(
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_offer.supplier_id,
            order_date=order_date.isoformat(),
            status="open",
            commit=False,
        )
        repos.purchase_orders.add_purchase_order_line(
            purchase_order_id=purchase_order_id,
            line_no=1,
            sku=target_sku,
            quantity_ordered=quantity,
            quantity_received=0,
            unit_cost=str(supplier_offer.unit_cost),
            commit=False,
        )
    return PurchaseOrderResult(
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_offer.supplier_id,
        supplier_name=supplier_offer.supplier_name,
        order_date=order_date,
        status="open",
        line_count=1,
        total_units=quantity,
        message=f"Created purchase order {purchase_order_id} for {target_sku}.",
    )


def receive_purchase_order(
    po_id: str,
    received_items: list[ReceiveItemInput],
    receive_date: date,
    repos: ProcurementRepositories,
) -> PurchaseOrderResult:
    """Receive some or all quantities on an open purchase order."""
    _ = receive_date
    po_bundle = repos.purchase_orders.get_open_purchase_order(po_id)
    if po_bundle is None:
        raise NotFoundError(f"Open purchase order '{po_id}' was not found.")

    _validate_received_items(po_bundle["lines"], received_items)
    update_purchase_order_receipt_state(po_id, received_items, repos)
    refreshed = repos.purchase_orders.get_purchase_order(po_id)
    assert refreshed is not None
    purchase_order = refreshed["purchase_order"]
    lines = refreshed["lines"]
    return PurchaseOrderResult(
        purchase_order_id=purchase_order["purchase_order_id"],
        supplier_id=purchase_order["supplier_id"],
        supplier_name=purchase_order["supplier_name"],
        order_date=date.fromisoformat(purchase_order["order_date"]),
        status=purchase_order["status"],
        line_count=len(lines),
        total_units=sum(int(line["quantity_ordered"]) for line in lines),
        message=f"Received items for purchase order {po_id}.",
    )


def update_purchase_order_receipt_state(
    po_id: str,
    received_items: list[ReceiveItemInput],
    repos: ProcurementRepositories,
) -> None:
    """Apply received quantities to PO lines and inventory, then refresh PO status."""
    po_bundle = repos.purchase_orders.get_open_purchase_order(po_id)
    if po_bundle is None:
        raise NotFoundError(f"Open purchase order '{po_id}' was not found.")

    line_by_sku = {line["sku"]: line for line in po_bundle["lines"]}
    conn = repos.purchase_orders.conn
    with conn:
        for item in received_items:
            repos.purchase_orders.update_purchase_order_line_received_qty(
                purchase_order_id=po_id,
                sku=item.sku,
                delta_received=item.quantity_received,
                commit=False,
            )
            repos.inventory.adjust_on_hand(item.sku, item.quantity_received, commit=False)

        refreshed = repos.purchase_orders.get_purchase_order(po_id)
        assert refreshed is not None
        status = _derive_purchase_order_status(refreshed["lines"])
        repos.purchase_orders.update_purchase_order_status(po_id, status, commit=False)


def _default_sku_for_product(product_id: str, catalog_repo: CatalogRepository) -> str:
    rows = catalog_repo.list_skus_for_product(product_id)
    if not rows:
        raise NotFoundError(f"Product '{product_id}' was not found in catalog.")
    return rows[0]["sku"]


def _validate_received_items(po_lines: list[dict], received_items: list[ReceiveItemInput]) -> None:
    if not received_items:
        raise ValidationError("At least one received item is required.")

    line_by_sku = {line["sku"]: line for line in po_lines}
    for item in received_items:
        if item.quantity_received <= 0:
            raise ValidationError("Received quantity must be greater than zero.")
        if item.sku not in line_by_sku:
            raise ValidationError(f"SKU '{item.sku}' is not on this purchase order.")
        line = line_by_sku[item.sku]
        remaining = int(line["quantity_ordered"]) - int(line["quantity_received"])
        if item.quantity_received > remaining:
            raise ValidationError(
                f"Received quantity exceeds remaining open quantity for {item.sku}: requested {item.quantity_received}, remaining {remaining}."
            )


def _derive_purchase_order_status(lines: list[dict]) -> str:
    fully_received = all(int(line["quantity_received"]) >= int(line["quantity_ordered"]) for line in lines)
    any_received = any(int(line["quantity_received"]) > 0 for line in lines)
    if fully_received:
        return "received"
    if any_received:
        return "partial"
    return "open"
