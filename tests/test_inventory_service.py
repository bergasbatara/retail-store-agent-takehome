from __future__ import annotations

from decimal import Decimal

from retail_agent.services.inventory_service import compute_product_days_of_cover


def test_days_of_cover_calculation_aggregates_by_product(inventory_repos):
    days = compute_product_days_of_cover("P-TOTE", inventory_repos)
    assert days == Decimal("12.00")

