"""Promotion creation and lookup workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from retail_agent.db.repositories import CatalogRepository, PromotionRepository
from retail_agent.exceptions import NotFoundError, ValidationError
from retail_agent.ids import next_promotion_id
from retail_agent.services.pricing_service import list_applicable_promotions
from retail_agent.types import Promotion, PromotionResult


PROMOTION_TYPE_PERCENT_OFF = "percent_off"
VALID_SCOPE_TYPES = {"product", "category"}


@dataclass(frozen=True)
class PromotionManagementRepositories:
    """Repository bundle used by promotion management."""

    catalog: CatalogRepository
    promotions: PromotionRepository


def create_promotion(
    scope_type: str,
    scope_ref: str,
    percent_off: Decimal,
    start_date: date,
    end_date: date,
    description: str,
    repos: PromotionManagementRepositories,
) -> PromotionResult:
    """Create and persist a percent-off promotion."""
    _validate_promotion_inputs(scope_type, percent_off, start_date, end_date, description)
    validate_promotion_scope(scope_type, scope_ref, repos)

    promo_id = next_promotion_id(repos.promotions.conn)
    repos.promotions.create_promotion(
        promo_id=promo_id,
        description=description,
        promo_type=PROMOTION_TYPE_PERCENT_OFF,
        value=str(percent_off),
        scope_type=scope_type,
        scope_ref=scope_ref,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    return PromotionResult(
        promo_id=promo_id,
        description=description,
        scope_type=scope_type,
        scope_ref=scope_ref,
        percent_off=percent_off,
        start_date=start_date,
        end_date=end_date,
        message=f"Created promotion {promo_id}.",
    )


def validate_promotion_scope(
    scope_type: str,
    scope_ref: str,
    repos: PromotionManagementRepositories,
) -> None:
    """Validate that the promotion scope points to a known product or category."""
    if scope_type not in VALID_SCOPE_TYPES:
        raise ValidationError(f"Promotion scope_type must be one of {sorted(VALID_SCOPE_TYPES)}.")

    if scope_type == "product":
        if not repos.catalog.list_skus_for_product(scope_ref):
            raise NotFoundError(f"Product '{scope_ref}' was not found.")
        return

    if scope_ref not in repos.catalog.list_categories():
        raise NotFoundError(f"Category '{scope_ref}' was not found.")


def list_promotions_for_sku(
    sku: str,
    target_date: date,
    repos: PromotionManagementRepositories,
) -> list[Promotion]:
    """List active promotions that apply to a concrete SKU."""
    return list_applicable_promotions(
        sku=sku,
        sale_date=target_date,
        promo_repo=repos.promotions,
        catalog_repo=repos.catalog,
    )


def _validate_promotion_inputs(
    scope_type: str,
    percent_off: Decimal,
    start_date: date,
    end_date: date,
    description: str,
) -> None:
    if scope_type not in VALID_SCOPE_TYPES:
        raise ValidationError(f"Promotion scope_type must be one of {sorted(VALID_SCOPE_TYPES)}.")
    if percent_off <= Decimal("0") or percent_off >= Decimal("100"):
        raise ValidationError("Promotion percent_off must be greater than 0 and less than 100.")
    if end_date < start_date:
        raise ValidationError("Promotion end_date must be on or after start_date.")
    if not description.strip():
        raise ValidationError("Promotion description is required.")
