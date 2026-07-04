"""Return processing workflow coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import InventoryRepository, OrderRepository, ReturnRepository
from retail_agent.domain.resolution import resolve_return_target
from retail_agent.exceptions import NotFoundError, ValidationError
from retail_agent.ids import next_return_id
from retail_agent.money import quantize_cents, to_decimal
from retail_agent.types import ReturnResult, SoldLine


GOOD_CONDITION = "good"
DAMAGED_CONDITION = "damaged"
VALID_RETURN_CONDITIONS = {GOOD_CONDITION, DAMAGED_CONDITION}


@dataclass(frozen=True)
class ReturnRepositories:
    """Repository bundle used by return processing."""

    inventory: InventoryRepository
    orders: OrderRepository
    returns: ReturnRepository


def process_return(
    order_id: str,
    sku_or_ref: str,
    quantity: int,
    condition: str,
    return_date: date,
    repos: ReturnRepositories,
) -> ReturnResult:
    """Process a return atomically, including inventory restock when applicable."""
    _validate_return_request(quantity, condition)
    resolved = resolve_return_target(order_id, sku_or_ref, repos.orders)
    sold_line = lookup_original_sale_line(order_id, resolved.sku, repos)
    validate_return_quantity(order_id, sold_line.sku, quantity, repos)
    refund_amount = compute_refund_amount(sold_line, quantity, sold_line.order_discount_pct)
    return_id = persist_return(
        {
            "order_id": order_id,
            "sku": sold_line.sku,
            "quantity": quantity,
            "condition": condition,
            "return_date": return_date,
            "refund_amount": refund_amount,
        },
        repos,
    )
    restocked_quantity = quantity if condition == GOOD_CONDITION else 0
    return ReturnResult(
        return_id=return_id,
        order_id=order_id,
        return_date=return_date,
        sku=sold_line.sku,
        quantity=quantity,
        condition=condition,
        refund_amount=refund_amount,
        restocked_quantity=restocked_quantity,
        message=f"Processed return {return_id} for order {order_id}.",
    )


def lookup_original_sale_line(
    order_id: str,
    sku: str,
    repos: ReturnRepositories,
) -> SoldLine:
    """Load the original sold line and paid-price context for a returned SKU."""
    bundle = repos.orders.get_order_with_lines(order_id)
    if bundle is None:
        raise NotFoundError(f"Order '{order_id}' was not found.")

    order = bundle["order"]
    for line in bundle["lines"]:
        if line["sku"] != sku:
            continue
        unit_price = to_decimal(line["unit_price"])
        order_discount_pct = to_decimal(order["order_discount_pct"])
        paid_unit_price = quantize_cents(
            unit_price * (Decimal("1") - (order_discount_pct / Decimal("100")))
        )
        return SoldLine(
            order_id=order_id,
            line_no=int(line["line_no"]),
            sku=line["sku"],
            product_id=line["product_id"],
            product_name=line["product_name"],
            quantity=int(line["quantity"]),
            unit_price=unit_price,
            order_discount_pct=order_discount_pct,
            paid_unit_price=paid_unit_price,
            color=line.get("color"),
            size=line.get("size"),
        )

    raise NotFoundError(f"SKU '{sku}' was not sold on order '{order_id}'.")


def compute_refund_amount(
    order_line: SoldLine,
    quantity: int,
    order_discount_pct: Decimal,
) -> Decimal:
    """Compute refund amount from the original paid unit price."""
    _ = order_discount_pct
    return quantize_cents(order_line.paid_unit_price * quantity)


def validate_return_quantity(
    order_id: str,
    sku: str,
    quantity: int,
    repos: ReturnRepositories,
) -> None:
    """Ensure the requested return quantity does not exceed remaining sold units."""
    if quantity <= 0:
        raise ValidationError("Return quantity must be greater than zero.")

    sold_line = lookup_original_sale_line(order_id, sku, repos)
    prior_returns = repos.returns.list_returns_for_order(order_id)
    returned_qty = sum(int(row["quantity"]) for row in prior_returns if row["sku"] == sku)
    remaining_qty = sold_line.quantity - returned_qty
    if quantity > remaining_qty:
        raise ValidationError(
            f"Return quantity exceeds remaining sold units for {sku}: requested {quantity}, remaining {remaining_qty}."
        )


def persist_return(
    return_record: dict,
    repos: ReturnRepositories,
) -> str:
    """Persist a return and restock inventory in the same transaction when needed."""
    return_id = next_return_id(repos.returns.conn)
    conn = repos.returns.conn
    with conn:
        repos.returns.create_return(
            return_id=return_id,
            return_date=return_record["return_date"].isoformat(),
            order_id=return_record["order_id"],
            sku=return_record["sku"],
            quantity=return_record["quantity"],
            condition=return_record["condition"],
            refund_amount=str(return_record["refund_amount"]),
            commit=False,
        )
        if return_record["condition"] == GOOD_CONDITION:
            repos.inventory.adjust_on_hand(
                return_record["sku"],
                return_record["quantity"],
                commit=False,
            )
    return return_id


def _validate_return_request(quantity: int, condition: str) -> None:
    if quantity <= 0:
        raise ValidationError("Return quantity must be greater than zero.")
    if condition not in VALID_RETURN_CONDITIONS:
        raise ValidationError(
            f"Return condition must be one of {sorted(VALID_RETURN_CONDITIONS)}."
        )
