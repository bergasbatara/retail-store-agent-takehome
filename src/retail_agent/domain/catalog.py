"""Catalog-level resolution helpers."""

from __future__ import annotations

from retail_agent.db.repositories import CatalogRepository
from retail_agent.exceptions import AmbiguityError, NotFoundError
from retail_agent.types import ProductResolution, ResolvedSku


def resolve_product_reference(name_or_sku: str, repo: CatalogRepository) -> ProductResolution:
    """Resolve a SKU or product name into a product-level candidate set."""
    sku_match = repo.get_sku(name_or_sku)
    if sku_match is not None:
        resolved = _row_to_resolved_sku(sku_match, quantity=1)
        return ProductResolution(
            query=name_or_sku,
            product_name=resolved.product_name,
            product_id=resolved.product_id,
            candidates=(resolved,),
        )

    candidates = repo.find_skus_by_product_name(name_or_sku)
    if not candidates:
        raise NotFoundError(f"No product found for '{name_or_sku}'.")

    resolved_candidates = tuple(_row_to_resolved_sku(row, quantity=1) for row in candidates)
    first = resolved_candidates[0]
    return ProductResolution(
        query=name_or_sku,
        product_name=first.product_name,
        product_id=first.product_id,
        candidates=resolved_candidates,
    )


def resolve_variant(
    product_name: str,
    color: str | None,
    size: str | None,
    repo: CatalogRepository,
) -> ResolvedSku:
    """Resolve a concrete sellable SKU from product and variant details."""
    candidates = repo.find_matching_variant(product_name, color, size)
    if not candidates:
        raise NotFoundError(f"No SKU found for '{product_name}'.")
    if len(candidates) > 1:
        raise AmbiguityError(
            f"Multiple variants match '{product_name}': {', '.join(_format_variant_candidate(row) for row in candidates)}"
        )
    return _row_to_resolved_sku(candidates[0], quantity=1)


def _row_to_resolved_sku(row: dict, *, quantity: int) -> ResolvedSku:
    return ResolvedSku(
        sku=row["sku"],
        product_id=row["product_id"],
        product_name=row["product_name"],
        quantity=quantity,
        category=row["category"],
        color=row.get("color"),
        size=row.get("size"),
        retail_price=row.get("retail_price"),
    )


def _format_variant_candidate(row: dict) -> str:
    parts = [row["product_name"]]
    if row.get("color"):
        parts.append(str(row["color"]))
    if row.get("size"):
        parts.append(str(row["size"]))
    parts.append(f"[{row['sku']}]")
    return " ".join(parts)
