"""CSV row mappers for seed data."""

from __future__ import annotations

from decimal import Decimal

from retail_agent.dates import parse_date
from retail_agent.money import to_decimal


def map_product_row(row: dict[str, str]) -> dict:
    return {
        "sku": row["sku"],
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "category": row["category"],
        "color": _blank_to_none(row["color"]),
        "size": _blank_to_none(row["size"]),
        "retail_price": to_decimal(row["retail_price"]),
    }


def map_customer_row(row: dict[str, str]) -> dict:
    return {
        "customer_id": row["customer_id"],
        "name": row["name"],
        "email": row["email"],
        "joined_date": parse_date(row["joined_date"]),
    }


def map_supplier_row(row: dict[str, str]) -> dict:
    return {
        "supplier_id": row["supplier_id"],
        "supplier_name": row["supplier_name"],
    }


def map_supplier_offer_row(row: dict[str, str]) -> dict:
    return {
        "supplier_id": row["supplier_id"],
        "product_id": row["product_id"],
        "unit_cost": to_decimal(row["unit_cost"]),
        "lead_time_days": int(row["lead_time_days"]),
    }


def map_inventory_row(row: dict[str, str]) -> dict:
    return {
        "sku": row["sku"],
        "on_hand_qty": int(row["on_hand_qty"]),
        "reorder_point": int(row["reorder_point"]),
        "reorder_qty": int(row["reorder_qty"]),
    }


def map_order_row(row: dict[str, str]) -> dict:
    return {
        "order_id": row["order_id"],
        "order_date": parse_date(row["order_date"]),
        "customer_id": _blank_to_none(row["customer_id"]),
        "order_discount_pct": to_decimal(row["order_discount_pct"]),
        "payment_method": row["payment_method"],
    }


def map_order_line_row(row: dict[str, str]) -> dict:
    return {
        "order_id": row["order_id"],
        "line_no": int(row["line_no"]),
        "sku": row["sku"],
        "quantity": int(row["quantity"]),
        "unit_price": to_decimal(row["unit_price"]),
    }


def map_return_row(row: dict[str, str]) -> dict:
    return {
        "return_id": row["return_id"],
        "return_date": parse_date(row["return_date"]),
        "order_id": row["order_id"],
        "sku": row["sku"],
        "quantity": int(row["quantity"]),
        "condition": row["condition"],
        "refund_amount": to_decimal(row["refund_amount"]),
    }


def map_promotion_row(row: dict[str, str]) -> dict:
    return {
        "promo_id": row["promo_id"],
        "description": row["description"],
        "type": row["type"],
        "value": to_decimal(row["value"]),
        "scope_type": row["scope_type"],
        "scope_ref": row["scope_ref"],
        "start_date": parse_date(row["start_date"]),
        "end_date": parse_date(row["end_date"]),
    }


def _blank_to_none(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None
