"""Catalog-level resolution helpers."""

from __future__ import annotations

import re

from retail_agent.db.repositories import CatalogRepository
from retail_agent.exceptions import AmbiguityError, NotFoundError
from retail_agent.types import ProductResolution, ResolvedSku


PRODUCT_NAME_ALIASES = {
    "canvas totes": "Canvas Tote",
    "canvas tote": "Canvas Tote",
    "classic tees": "Classic Tee",
    "classic tee": "Classic Tee",
    "standard tee": "Classic Tee",
    "standard tees": "Classic Tee",
    "tee": "Classic Tee",
    "tees": "Classic Tee",
    "hoodie": "Pullover Hoodie",
    "hoodies": "Pullover Hoodie",
    "pullover hoodies": "Pullover Hoodie",
    "mug": "Ceramic Mug",
    "mugs": "Ceramic Mug",
    "sock": "Wool Socks",
    "socks": "Wool Socks",
}

COLOR_ALIASES = {
    "grey": "Gray",
}

SIZE_ALIASES = {
    "small": "S",
    "s": "S",
    "medium": "M",
    "med": "M",
    "m": "M",
    "large": "L",
    "lg": "L",
    "l": "L",
}


def candidate_reference_terms(raw_value: str) -> tuple[str, ...]:
    """Return normalized reference candidates for product names and SKU-like inputs."""
    stripped = " ".join(raw_value.strip().split())
    if not stripped:
        return ()

    candidates: list[str] = []
    _append_reference_variants(candidates, stripped)

    deindexed = _strip_numeric_suffix(stripped)
    if deindexed != stripped:
        _append_reference_variants(candidates, deindexed)

    sku_words = _sku_like_words_to_phrase(stripped)
    if sku_words and sku_words != stripped:
        _append_reference_variants(candidates, sku_words)

    deindexed_words = _sku_like_words_to_phrase(deindexed)
    if deindexed_words and deindexed_words not in {stripped, deindexed}:
        _append_reference_variants(candidates, deindexed_words)

    return tuple(candidates)


def resolve_product_reference(name_or_sku: str, repo: CatalogRepository) -> ProductResolution:
    """Resolve a SKU or product name into a product-level candidate set."""
    for reference in candidate_reference_terms(name_or_sku):
        sku_match = repo.get_sku(reference)
        if sku_match is not None:
            resolved = _row_to_resolved_sku(sku_match, quantity=1)
            return ProductResolution(
                query=name_or_sku,
                product_name=resolved.product_name,
                product_id=resolved.product_id,
                candidates=(resolved,),
            )

    resolved_name, candidates = _resolve_product_name_candidates(name_or_sku, repo)
    if not candidates:
        raise NotFoundError(f"No product found for '{name_or_sku}'.")

    resolved_candidates = tuple(_row_to_resolved_sku(row, quantity=1) for row in candidates)
    first = resolved_candidates[0]
    return ProductResolution(
        query=name_or_sku,
        product_name=resolved_name or first.product_name,
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
    normalized_color = _normalize_color(color)
    normalized_size = _normalize_size(size)
    resolved_name, candidates = _resolve_variant_candidates(
        product_name,
        normalized_color,
        normalized_size,
        repo,
    )
    if not candidates:
        raise NotFoundError(f"No SKU found for '{product_name}'.")
    if len(candidates) > 1:
        raise AmbiguityError(
            _build_variant_ambiguity_message(
                resolved_name or product_name,
                normalized_color,
                normalized_size,
                candidates,
            )
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


def _build_variant_ambiguity_message(
    product_name: str,
    color: str | None,
    size: str | None,
    candidates: list[dict],
) -> str:
    if color is None and len({row.get("color") for row in candidates}) > 1:
        colors = ", ".join(
            sorted({str(row["color"]) for row in candidates if row.get("color")})
        )
        return f"Multiple {product_name} variants match. Which color did you want? Options: {colors}."
    if size is None and len({row.get("size") for row in candidates}) > 1:
        sizes = ", ".join(
            sorted({str(row["size"]) for row in candidates if row.get("size")})
        )
        return f"Multiple {product_name} variants match. Which size did you want? Options: {sizes}."
    return (
        f"Multiple variants match '{product_name}'. "
        f"Please specify the missing variant detail. Options: {', '.join(_format_variant_candidate(row) for row in candidates)}"
    )


def _resolve_product_name_candidates(
    raw_name: str,
    repo: CatalogRepository,
) -> tuple[str | None, list[dict]]:
    for candidate_name in candidate_reference_terms(raw_name):
        candidates = repo.find_skus_by_product_name(candidate_name)
        if candidates:
            return candidate_name, candidates
    return None, []


def _resolve_variant_candidates(
    raw_name: str,
    color: str | None,
    size: str | None,
    repo: CatalogRepository,
) -> tuple[str | None, list[dict]]:
    for candidate_name in candidate_reference_terms(raw_name):
        candidates = repo.find_matching_variant(candidate_name, color, size)
        if candidates:
            return candidate_name, candidates
    return None, []


def _append_reference_variants(candidates: list[str], raw_name: str) -> None:
    stripped = " ".join(raw_name.strip().split())
    if not stripped:
        return

    _append_unique(candidates, stripped)

    alias = PRODUCT_NAME_ALIASES.get(stripped.lower())
    if alias is not None:
        _append_unique(candidates, alias)

    singularized = _singularize_product_name(stripped)
    if singularized != stripped:
        _append_unique(candidates, singularized)
        alias = PRODUCT_NAME_ALIASES.get(singularized.lower())
        if alias is not None:
            _append_unique(candidates, alias)

    normalized_case = _title_case_name(stripped)
    if normalized_case != stripped:
        _append_unique(candidates, normalized_case)
        alias = PRODUCT_NAME_ALIASES.get(normalized_case.lower())
        if alias is not None:
            _append_unique(candidates, alias)


def _singularize_product_name(name: str) -> str:
    parts = name.split()
    if not parts:
        return name
    last = parts[-1]
    lowered = last.lower()
    if lowered.endswith("ies") and len(last) > 3:
        parts[-1] = last[:-3] + "y"
    elif lowered.endswith("es") and len(last) > 2 and lowered not in {"tees"}:
        parts[-1] = last[:-2]
    elif lowered.endswith("s") and len(last) > 1:
        parts[-1] = last[:-1]
    return " ".join(parts)


def _title_case_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).title()


def _strip_numeric_suffix(value: str) -> str:
    return re.sub(r"[-_]\d{1,4}$", "", value.strip())


def _sku_like_words_to_phrase(value: str) -> str | None:
    normalized = value.replace("_", "-").strip("- ")
    if "-" not in normalized:
        return None
    words = [part for part in normalized.split("-") if part and not part.isdigit()]
    if not words:
        return None
    return " ".join(words)


def _append_unique(values: list[str], candidate: str) -> None:
    if candidate not in values:
        values.append(candidate)


def _normalize_color(color: str | None) -> str | None:
    if color is None:
        return None
    stripped = " ".join(color.strip().split())
    if not stripped:
        return None
    alias = COLOR_ALIASES.get(stripped.lower())
    if alias is not None:
        return alias
    return _title_case_name(stripped)


def _normalize_size(size: str | None) -> str | None:
    if size is None:
        return None
    stripped = " ".join(size.strip().split())
    if not stripped:
        return None
    alias = SIZE_ALIASES.get(stripped.lower())
    if alias is not None:
        return alias
    return stripped.upper()
