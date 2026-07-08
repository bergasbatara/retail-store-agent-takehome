"""Cross-entity resolution helpers for sales and returns."""

from __future__ import annotations

from retail_agent.domain.catalog import resolve_product_reference, resolve_variant
from retail_agent.db.repositories import CatalogRepository, OrderRepository
from retail_agent.exceptions import AmbiguityError, NotFoundError, ValidationError
from retail_agent.types import ResolvedReturnItem, ResolvedSku, SaleItemInput


def resolve_sale_items(
    raw_items: list[SaleItemInput] | tuple[SaleItemInput, ...],
    catalog_repo: CatalogRepository,
) -> list[ResolvedSku]:
    """Resolve requested sale items into concrete SKUs."""
    resolved_items: list[ResolvedSku] = []
    for item in raw_items:
        if item.quantity <= 0:
            raise ValidationError("Sale item quantity must be greater than zero.")

        if item.sku:
            resolution = resolve_product_reference(item.sku, catalog_repo)
            candidate = resolution.candidates[0]
            resolved_items.append(_with_quantity(candidate, item.quantity))
            continue

        candidate = resolve_variant(item.product_name, item.color, item.size, catalog_repo)
        resolved_items.append(_with_quantity(candidate, item.quantity))
    return resolved_items


def resolve_return_target(
    order_id: str,
    sku_or_description: str,
    repo: OrderRepository,
) -> ResolvedReturnItem:
    """Resolve a return reference against a concrete line on an order."""
    order_bundle = repo.get_order_with_lines(order_id)
    if order_bundle is None:
        raise NotFoundError(f"Order '{order_id}' was not found.")

    lines = order_bundle["lines"]
    if not lines:
        raise NotFoundError(f"Order '{order_id}' has no lines.")

    exact_matches = [line for line in lines if line["sku"].lower() == sku_or_description.lower()]
    if len(exact_matches) == 1:
        return _to_resolved_return_item(order_id, exact_matches[0])
    if len(exact_matches) > 1:
        raise AmbiguityError(build_ambiguity_message(exact_matches))

    query = sku_or_description.lower()
    fuzzy_matches = [
        line
        for line in lines
        if query in line["product_name"].lower()
        or query in _variant_descriptor(line).lower()
    ]
    if not fuzzy_matches:
        raise NotFoundError(f"No returnable item on order '{order_id}' matches '{sku_or_description}'.")
    if len(fuzzy_matches) > 1:
        raise AmbiguityError(build_ambiguity_message(fuzzy_matches))
    return _to_resolved_return_item(order_id, fuzzy_matches[0])


def build_ambiguity_message(candidates: list[dict]) -> str:
    """Build a user-facing ambiguity message from candidate rows."""
    formatted = ", ".join(_variant_descriptor(candidate) for candidate in candidates)
    return f"Ambiguous match. Please specify the exact item. Options: {formatted}"


def _with_quantity(candidate: ResolvedSku, quantity: int) -> ResolvedSku:
    return ResolvedSku(
        sku=candidate.sku,
        product_id=candidate.product_id,
        product_name=candidate.product_name,
        quantity=quantity,
        category=candidate.category,
        color=candidate.color,
        size=candidate.size,
        retail_price=candidate.retail_price,
    )


def _to_resolved_return_item(order_id: str, line: dict) -> ResolvedReturnItem:
    return ResolvedReturnItem(
        order_id=order_id,
        sku=line["sku"],
        product_id=line["product_id"],
        product_name=line["product_name"],
        quantity_purchased=line["quantity"],
        color=line.get("color"),
        size=line.get("size"),
    )


def _variant_descriptor(line: dict) -> str:
    parts = [line["product_name"]]
    if line.get("color"):
        parts.append(str(line["color"]))
    if line.get("size"):
        parts.append(str(line["size"]))
    parts.append(f"[{line['sku']}]")
    return " ".join(parts)
