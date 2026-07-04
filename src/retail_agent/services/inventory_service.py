"""Inventory mutation and stock-risk logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import InventoryRepository, OrderRepository
from retail_agent.exceptions import InsufficientInventoryError, NotFoundError, ValidationError
from retail_agent.money import quantize_cents, to_decimal
from retail_agent.types import InventorySnapshot, ResolvedSku, StockoutAlert


VELOCITY_PERIOD_START = date(2026, 5, 1)
VELOCITY_PERIOD_END = date(2026, 5, 31)
LOW_DAYS_OF_COVER_THRESHOLD = Decimal("14")
THIRTY_DAYS = Decimal("30")


@dataclass(frozen=True)
class InventoryRepositories:
    """Repository bundle used by inventory operations."""

    inventory: InventoryRepository
    orders: OrderRepository


def assert_inventory_available(
    sku: str,
    quantity: int,
    inventory_repo: InventoryRepository,
) -> None:
    """Raise when on-hand quantity is insufficient for a requested SKU."""
    if quantity <= 0:
        raise ValidationError("Inventory quantity must be greater than zero.")

    snapshot = get_inventory_snapshot(sku, inventory_repo)
    if snapshot.on_hand_qty < quantity:
        raise InsufficientInventoryError(
            f"Insufficient inventory for {sku}: requested {quantity}, available {snapshot.on_hand_qty}."
        )


def reserve_or_decrement_inventory(
    items: list[ResolvedSku],
    inventory_repo: InventoryRepository,
) -> None:
    """Validate and decrement inventory for a list of resolved sale items."""
    for item in items:
        assert_inventory_available(item.sku, item.quantity, inventory_repo)
    for item in items:
        inventory_repo.adjust_on_hand(item.sku, -item.quantity)


def restock_good_return(
    sku: str,
    quantity: int,
    inventory_repo: InventoryRepository,
) -> None:
    """Restock sellable units returned in good condition."""
    if quantity <= 0:
        raise ValidationError("Restock quantity must be greater than zero.")
    get_inventory_snapshot(sku, inventory_repo)
    inventory_repo.adjust_on_hand(sku, quantity)


def receive_inventory(
    sku: str,
    quantity: int,
    inventory_repo: InventoryRepository,
) -> None:
    """Increase inventory when supplier units are received."""
    if quantity <= 0:
        raise ValidationError("Received quantity must be greater than zero.")
    get_inventory_snapshot(sku, inventory_repo)
    inventory_repo.adjust_on_hand(sku, quantity)


def get_inventory_snapshot(
    sku: str,
    inventory_repo: InventoryRepository,
) -> InventorySnapshot:
    """Return a typed inventory snapshot for a SKU."""
    row = inventory_repo.get_inventory_for_sku(sku)
    if row is None:
        raise NotFoundError(f"Inventory record for SKU '{sku}' was not found.")
    return InventorySnapshot(
        sku=row["sku"],
        product_id=row["product_id"],
        product_name=row["product_name"],
        category=row["category"],
        on_hand_qty=int(row["on_hand_qty"]),
        reorder_point=int(row["reorder_point"]),
        reorder_qty=int(row["reorder_qty"]),
        color=row.get("color"),
        size=row.get("size"),
    )


def compute_product_days_of_cover(
    product_id: str,
    repos: InventoryRepositories,
) -> Decimal | None:
    """Compute product-level days of cover across all variants."""
    inventory_rows = repos.inventory.list_inventory_for_product(product_id)
    if not inventory_rows:
        raise NotFoundError(f"No inventory rows found for product '{product_id}'.")

    monthly_units = _monthly_units_by_product(repos.orders).get(product_id, 0)
    if monthly_units <= 0:
        return None

    total_on_hand = sum(int(row["on_hand_qty"]) for row in inventory_rows)
    days_of_cover = to_decimal(total_on_hand) / (to_decimal(monthly_units) / THIRTY_DAYS)
    return quantize_cents(days_of_cover)


def list_stockout_risks(
    as_of_date: date,
    repos: InventoryRepositories,
) -> list[StockoutAlert]:
    """List products that are below reorder point or under 14 days of cover."""
    _ = as_of_date
    inventory_rows = repos.inventory.list_all_inventory()
    monthly_units_map = _monthly_units_by_product(repos.orders)

    product_rows: dict[str, list[dict]] = {}
    for row in inventory_rows:
        product_rows.setdefault(row["product_id"], []).append(row)

    alerts: list[StockoutAlert] = []
    for product_id, rows in product_rows.items():
        total_on_hand = sum(int(row["on_hand_qty"]) for row in rows)
        total_reorder_point = sum(int(row["reorder_point"]) for row in rows)
        monthly_units = int(monthly_units_map.get(product_id, 0))
        days_of_cover = _compute_days_of_cover(total_on_hand, monthly_units)
        below_reorder_point = total_on_hand <= total_reorder_point
        low_days_of_cover = days_of_cover is not None and days_of_cover < LOW_DAYS_OF_COVER_THRESHOLD

        if not below_reorder_point and not low_days_of_cover:
            continue

        alerts.append(
            StockoutAlert(
                product_id=product_id,
                product_name=rows[0]["product_name"],
                on_hand_qty=total_on_hand,
                reorder_point=total_reorder_point,
                monthly_units=monthly_units,
                days_of_cover=days_of_cover,
                below_reorder_point=below_reorder_point,
                low_days_of_cover=low_days_of_cover,
                reason=_build_stockout_reason(below_reorder_point, low_days_of_cover, days_of_cover),
            )
        )

    alerts.sort(key=lambda alert: (not alert.below_reorder_point, alert.days_of_cover or Decimal("999999"), alert.product_name))
    return alerts


def _monthly_units_by_product(order_repo: OrderRepository) -> dict[str, int]:
    rows = order_repo.list_units_sold_by_product(VELOCITY_PERIOD_START, VELOCITY_PERIOD_END)
    return {row["product_id"]: int(row["units_sold"]) for row in rows}


def _compute_days_of_cover(total_on_hand: int, monthly_units: int) -> Decimal | None:
    if monthly_units <= 0:
        return None
    days_of_cover = to_decimal(total_on_hand) / (to_decimal(monthly_units) / THIRTY_DAYS)
    return quantize_cents(days_of_cover)


def _build_stockout_reason(
    below_reorder_point: bool,
    low_days_of_cover: bool,
    days_of_cover: Decimal | None,
) -> str:
    if below_reorder_point and low_days_of_cover and days_of_cover is not None:
        return f"Below reorder point and only {days_of_cover} days of cover remaining."
    if below_reorder_point:
        return "Below reorder point."
    if low_days_of_cover and days_of_cover is not None:
        return f"Only {days_of_cover} days of cover remaining."
    return ""
