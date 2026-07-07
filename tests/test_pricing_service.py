from __future__ import annotations

from datetime import date
from decimal import Decimal

from retail_agent.services.pricing_service import (
    choose_best_promotion,
    compute_effective_unit_price,
)


def test_tee_promo_price_during_seed_window(catalog_repo, promotion_repo):
    price = compute_effective_unit_price(
        "TEE-BLU-M",
        date(2026, 5, 2),
        promotion_repo,
        catalog_repo,
    )
    assert price == Decimal("20.00")


def test_hoodie_20_percent_promo_returns_48(catalog_repo, promotion_repo):
    promotion_repo.create_promotion(
        "PR-900",
        "Hoodie promo",
        "percent_off",
        "20",
        "product",
        "P-HOOD",
        "2026-06-20",
        "2026-06-22",
    )

    price = compute_effective_unit_price(
        "HOOD-GRY-M",
        date(2026, 6, 21),
        promotion_repo,
        catalog_repo,
    )
    assert price == Decimal("48.00")


def test_overlapping_promo_chooses_lower_price(catalog_repo, promotion_repo):
    promotion_repo.create_promotion(
        "PR-901",
        "Hoodie promo",
        "percent_off",
        "20",
        "product",
        "P-HOOD",
        "2026-06-20",
        "2026-06-22",
    )
    promotion_repo.create_promotion(
        "PR-902",
        "Apparel promo",
        "percent_off",
        "10",
        "category",
        "apparel",
        "2026-06-20",
        "2026-06-22",
    )

    chosen = choose_best_promotion(
        "HOOD-GRY-M",
        date(2026, 6, 21),
        promotion_repo,
        catalog_repo,
    )
    assert chosen is not None
    assert chosen.promo_id == "PR-901"

