"""Validation for normalized seed data."""

from __future__ import annotations

from decimal import Decimal

from retail_agent.exceptions import ValidationError
from retail_agent.types import SeedDataBundle


def validate_seed_bundle(bundle: SeedDataBundle) -> None:
    """Validate the full normalized seed bundle."""
    validate_foreign_key_shapes(bundle)
    validate_money_fields(bundle)


def validate_foreign_key_shapes(bundle: SeedDataBundle) -> None:
    """Ensure normalized seed rows reference known entities."""
    sku_ids = {row["sku"] for row in bundle.products}
    product_ids = {row["product_id"] for row in bundle.products}
    customer_ids = {row["customer_id"] for row in bundle.customers}
    supplier_ids = {row["supplier_id"] for row in bundle.suppliers}
    order_ids = {row["order_id"] for row in bundle.orders}

    for row in bundle.supplier_catalog:
        _assert_in(row["supplier_id"], supplier_ids, "supplier_catalog.supplier_id")
        _assert_in(row["product_id"], product_ids, "supplier_catalog.product_id")

    for row in bundle.inventory:
        _assert_in(row["sku"], sku_ids, "inventory.sku")

    for row in bundle.orders:
        if row["customer_id"] is not None:
            _assert_in(row["customer_id"], customer_ids, "orders.customer_id")

    for row in bundle.order_lines:
        _assert_in(row["order_id"], order_ids, "order_lines.order_id")
        _assert_in(row["sku"], sku_ids, "order_lines.sku")

    for row in bundle.returns:
        _assert_in(row["order_id"], order_ids, "returns.order_id")
        _assert_in(row["sku"], sku_ids, "returns.sku")

    for row in bundle.promotions:
        if row["scope_type"] == "product":
            _assert_in(row["scope_ref"], product_ids, "promotions.scope_ref")


def validate_money_fields(bundle: SeedDataBundle) -> None:
    """Ensure normalized money fields were parsed to Decimal."""
    decimal_fields = (
        (bundle.products, "retail_price"),
        (bundle.supplier_catalog, "unit_cost"),
        (bundle.orders, "order_discount_pct"),
        (bundle.order_lines, "unit_price"),
        (bundle.returns, "refund_amount"),
        (bundle.promotions, "value"),
    )
    for rows, field_name in decimal_fields:
        for row in rows:
            if not isinstance(row[field_name], Decimal):
                raise ValidationError(f"{field_name} must be Decimal, got {type(row[field_name]).__name__}")


def _assert_in(value: str, valid_values: set[str], field_name: str) -> None:
    if value not in valid_values:
        raise ValidationError(f"{field_name} references unknown value: {value}")
