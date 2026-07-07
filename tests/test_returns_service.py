from __future__ import annotations

from datetime import date
from decimal import Decimal

from retail_agent.services.returns_service import process_return


def test_o1006_hoodie_refund_equals_54(return_repos, inventory_repo):
    before = inventory_repo.get_inventory_for_sku("HOOD-NVY-L")
    result = process_return(
        order_id="O-1006",
        sku_or_ref="HOOD-NVY-L",
        quantity=1,
        condition="good",
        return_date=date(2026, 6, 19),
        repos=return_repos,
    )
    after = inventory_repo.get_inventory_for_sku("HOOD-NVY-L")

    assert result.refund_amount == Decimal("54.00")
    assert result.restocked_quantity == 1
    assert after["on_hand_qty"] == before["on_hand_qty"] + 1


def test_damaged_tote_return_does_not_restock(return_repos, inventory_repo):
    before = inventory_repo.get_inventory_for_sku("TOTE")
    result = process_return(
        order_id="O-1006",
        sku_or_ref="TOTE",
        quantity=1,
        condition="damaged",
        return_date=date(2026, 6, 19),
        repos=return_repos,
    )
    after = inventory_repo.get_inventory_for_sku("TOTE")

    assert result.refund_amount == Decimal("16.20")
    assert result.restocked_quantity == 0
    assert after["on_hand_qty"] == before["on_hand_qty"]

