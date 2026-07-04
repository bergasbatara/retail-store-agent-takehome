"""Pricing and promotion logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.dates import parse_date
from retail_agent.db.repositories import CatalogRepository, PromotionRepository
from retail_agent.exceptions import NotFoundError
from retail_agent.money import apply_percent_discount, quantize_cents, to_decimal
from retail_agent.types import PricedLine, Promotion, ResolvedSku


@dataclass(frozen=True)
class PricingRepositories:
    """Repository bundle used by pricing operations."""

    catalog: CatalogRepository
    promotions: PromotionRepository


def get_base_price_for_sku(sku: str, catalog_repo: CatalogRepository) -> Decimal:
    """Return the list price for a concrete SKU."""
    row = catalog_repo.get_sku(sku)
    if row is None:
        raise NotFoundError(f"SKU '{sku}' was not found.")
    return to_decimal(row["retail_price"])


def list_applicable_promotions(
    sku: str,
    sale_date: date,
    promo_repo: PromotionRepository,
    catalog_repo: CatalogRepository,
) -> list[Promotion]:
    """Return all active promotions whose scope matches the SKU."""
    sku_row = catalog_repo.get_sku(sku)
    if sku_row is None:
        raise NotFoundError(f"SKU '{sku}' was not found.")

    promotions = [
        _row_to_promotion(row)
        for row in promo_repo.list_active_promotions(sale_date)
        if _promotion_applies_to_sku(row, sku_row)
    ]
    return promotions


def choose_best_promotion(
    sku: str,
    sale_date: date,
    promo_repo: PromotionRepository,
    catalog_repo: CatalogRepository,
) -> Promotion | None:
    """Choose the active promotion that yields the lowest unit price."""
    base_price = get_base_price_for_sku(sku, catalog_repo)
    applicable = list_applicable_promotions(sku, sale_date, promo_repo, catalog_repo)
    if not applicable:
        return None

    return min(
        applicable,
        key=lambda promotion: (
            apply_percent_discount(base_price, promotion.value),
            promotion.promo_id,
        ),
    )


def compute_effective_unit_price(
    sku: str,
    sale_date: date,
    promo_repo: PromotionRepository,
    catalog_repo: CatalogRepository,
) -> Decimal:
    """Compute the per-unit price after the best active item-level promotion."""
    base_price = get_base_price_for_sku(sku, catalog_repo)
    promotion = choose_best_promotion(sku, sale_date, promo_repo, catalog_repo)
    if promotion is None:
        return quantize_cents(base_price)
    return apply_percent_discount(base_price, promotion.value)


def compute_paid_unit_price(unit_price: Decimal, order_discount_pct: Decimal) -> Decimal:
    """Compute the actual paid unit price after order-level discount proration."""
    return apply_percent_discount(unit_price, order_discount_pct)


def price_sale_items(
    items: list[ResolvedSku],
    sale_date: date,
    order_discount_pct: Decimal,
    repos: PricingRepositories,
) -> list[PricedLine]:
    """Price resolved sale items without mutating application state."""
    priced_lines: list[PricedLine] = []
    for item in items:
        base_unit_price = get_base_price_for_sku(item.sku, repos.catalog)
        applied_promotion = choose_best_promotion(
            item.sku,
            sale_date,
            repos.promotions,
            repos.catalog,
        )
        effective_unit_price = (
            apply_percent_discount(base_unit_price, applied_promotion.value)
            if applied_promotion is not None
            else quantize_cents(base_unit_price)
        )
        paid_unit_price = compute_paid_unit_price(effective_unit_price, order_discount_pct)
        priced_lines.append(
            PricedLine(
                sku=item.sku,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                category=item.category,
                color=item.color,
                size=item.size,
                base_unit_price=base_unit_price,
                effective_unit_price=effective_unit_price,
                paid_unit_price=paid_unit_price,
                applied_promotion=applied_promotion,
            )
        )
    return priced_lines


def _promotion_applies_to_sku(promotion_row: dict, sku_row: dict) -> bool:
    if promotion_row["scope_type"] == "product":
        return promotion_row["scope_ref"] == sku_row["product_id"]
    if promotion_row["scope_type"] == "category":
        return promotion_row["scope_ref"] == sku_row["category"]
    return False


def _row_to_promotion(row: dict) -> Promotion:
    return Promotion(
        promo_id=row["promo_id"],
        description=row["description"],
        type=row["type"],
        value=to_decimal(row["value"]),
        scope_type=row["scope_type"],
        scope_ref=row["scope_ref"],
        start_date=row["start_date"] if isinstance(row["start_date"], date) else parse_date(row["start_date"]),
        end_date=row["end_date"] if isinstance(row["end_date"], date) else parse_date(row["end_date"]),
    )
