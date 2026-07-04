"""Deterministic reporting and analytics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import (
    InventoryRepository,
    OrderRepository,
    ReturnRepository,
    SupplierRepository,
)
from retail_agent.exceptions import NotFoundError
from retail_agent.money import quantize_cents, to_decimal
from retail_agent.services.inventory_service import (
    InventoryRepositories,
    list_stockout_risks,
)
from retail_agent.types import MarginReportRow, StockoutAlert


NORTHWIND_SUPPLIER_ID = "SUP-NW"


@dataclass(frozen=True)
class ReportingRepositories:
    """Repository bundle used by analytics queries."""

    inventory: InventoryRepository
    orders: OrderRepository
    returns: ReturnRepository
    suppliers: SupplierRepository


def compute_product_revenue(
    product_id: str,
    period_start: date,
    period_end: date,
    repos: ReportingRepositories,
) -> Decimal:
    """Compute net product revenue for the period after refunds for that product."""
    gross_revenue = Decimal("0")
    for line in repos.orders.list_product_sales_lines(period_start, period_end):
        if line["product_id"] != product_id:
            continue
        paid_unit_price = _paid_unit_price(line["unit_price"], line["order_discount_pct"])
        gross_revenue += paid_unit_price * int(line["quantity"])

    refunds = Decimal("0")
    for refund in repos.returns.list_returns_for_period(period_start, period_end):
        if refund["product_id"] != product_id:
            continue
        refunds += to_decimal(refund["refund_amount"])

    return quantize_cents(gross_revenue - refunds)


def compute_product_margin(
    product_id: str,
    period_start: date,
    period_end: date,
    repos: ReportingRepositories,
) -> Decimal:
    """Compute product margin for the period using refunded units and cost basis."""
    revenue = compute_product_revenue(product_id, period_start, period_end, repos)
    sold_units = 0
    for line in repos.orders.list_product_sales_lines(period_start, period_end):
        if line["product_id"] == product_id:
            sold_units += int(line["quantity"])

    returned_units = 0
    for refund in repos.returns.list_returns_for_period(period_start, period_end):
        if refund["product_id"] == product_id:
            returned_units += int(refund["quantity"])

    units_kept_sold = max(0, sold_units - returned_units)
    unit_cost = _northwind_unit_cost(product_id, repos.suppliers)
    cost = quantize_cents(unit_cost * units_kept_sold)
    return quantize_cents(revenue - cost)


def top_products_by_margin(
    limit: int,
    period_start: date,
    period_end: date,
    repos: ReportingRepositories,
) -> list[MarginReportRow]:
    """Return products ranked by margin descending for the period."""
    sales_rows = repos.orders.list_product_sales_lines(period_start, period_end)
    if not sales_rows:
        return []

    product_names: dict[str, str] = {}
    sold_units: dict[str, int] = defaultdict(int)
    for line in sales_rows:
        product_id = line["product_id"]
        product_names[product_id] = line["product_name"]
        sold_units[product_id] += int(line["quantity"])

    rows: list[MarginReportRow] = []
    for product_id, units in sold_units.items():
        revenue = compute_product_revenue(product_id, period_start, period_end, repos)
        margin = compute_product_margin(product_id, period_start, period_end, repos)
        unit_cost = _northwind_unit_cost(product_id, repos.suppliers)
        returned_units = sum(
            int(refund["quantity"])
            for refund in repos.returns.list_returns_for_period(period_start, period_end)
            if refund["product_id"] == product_id
        )
        cost = quantize_cents(unit_cost * max(0, units - returned_units))
        rows.append(
            MarginReportRow(
                product_id=product_id,
                product_name=product_names[product_id],
                units_sold=units,
                revenue=revenue,
                cost=cost,
                margin=margin,
            )
        )

    rows.sort(key=lambda row: (-row.margin, row.product_name))
    return rows[:limit]


def net_revenue_for_period(
    period_start: date,
    period_end: date,
    repos: ReportingRepositories,
) -> Decimal:
    """Compute period net revenue after refunds issued in the period."""
    gross_revenue = Decimal("0")
    for line in repos.orders.list_product_sales_lines(period_start, period_end):
        paid_unit_price = _paid_unit_price(line["unit_price"], line["order_discount_pct"])
        gross_revenue += paid_unit_price * int(line["quantity"])

    refunds = sum(
        (to_decimal(refund["refund_amount"]) for refund in repos.returns.list_returns_for_period(period_start, period_end)),
        Decimal("0"),
    )
    return quantize_cents(gross_revenue - refunds)


def monthly_units_sold_by_product(
    period_start: date,
    period_end: date,
    repos: ReportingRepositories,
) -> dict[str, int]:
    """Return units sold by product for the period."""
    rows = repos.orders.list_units_sold_by_product(period_start, period_end)
    return {row["product_id"]: int(row["units_sold"]) for row in rows}


def stockout_report(
    as_of_date: date,
    repos: ReportingRepositories,
) -> list[StockoutAlert]:
    """Return stock-out alerts using the inventory service calculations."""
    return list_stockout_risks(
        as_of_date,
        InventoryRepositories(inventory=repos.inventory, orders=repos.orders),
    )


def _paid_unit_price(unit_price: str | Decimal, order_discount_pct: str | Decimal) -> Decimal:
    unit = to_decimal(unit_price)
    discount = to_decimal(order_discount_pct)
    return quantize_cents(unit * (Decimal("1") - (discount / Decimal("100"))))


def _northwind_unit_cost(product_id: str, supplier_repo: SupplierRepository) -> Decimal:
    for offer in supplier_repo.list_supplier_offers(product_id):
        if offer["supplier_id"] == NORTHWIND_SUPPLIER_ID:
            return to_decimal(offer["unit_cost"])
    raise NotFoundError(f"Northwind cost basis not found for product '{product_id}'.")
