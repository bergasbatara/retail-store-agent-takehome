from __future__ import annotations

from datetime import date
from decimal import Decimal

from retail_agent.services.reporting_service import stockout_report, top_products_by_margin


def test_top_products_by_margin_for_may_2026_are_deterministic(reporting_repos):
    rows = top_products_by_margin(
        5,
        date(2026, 5, 1),
        date(2026, 5, 31),
        reporting_repos,
    )

    assert [row.product_id for row in rows] == [
        "P-TEE",
        "P-HOOD",
        "P-SOCK",
        "P-TOTE",
        "P-MUG",
    ]
    assert rows[0].margin == Decimal("420.00")
    assert rows[1].margin == Decimal("282.00")


def test_stockout_report_flags_tote(reporting_repos):
    rows = stockout_report(date(2026, 6, 19), reporting_repos)

    assert len(rows) == 1
    tote = rows[0]
    assert tote.product_id == "P-TOTE"
    assert tote.below_reorder_point is True
    assert tote.low_days_of_cover is True

