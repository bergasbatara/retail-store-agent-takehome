from __future__ import annotations

from datetime import date

from retail_agent.services.procurement_service import (
    create_reorder_purchase_orders,
    receive_purchase_order,
    select_best_supplier,
)
from retail_agent.types import ReceiveItemInput


def test_tote_reorders_choose_northwind_over_too_slow_pioneer(procurement_repos):
    supplier = select_best_supplier("P-TOTE", procurement_repos.suppliers)
    assert supplier.supplier_id == "SUP-NW"

    results = create_reorder_purchase_orders(date(2026, 6, 19), procurement_repos)
    assert len(results) == 1
    assert results[0].supplier_id == "SUP-NW"
    assert results[0].total_units == 50


def test_partial_receipt_updates_open_quantity(procurement_repos, purchase_order_repo, inventory_repo):
    create_reorder_purchase_orders(date(2026, 6, 19), procurement_repos)
    before = inventory_repo.get_inventory_for_sku("TOTE")

    result = receive_purchase_order(
        "PO-0001",
        [ReceiveItemInput(sku="TOTE", quantity_received=40)],
        date(2026, 6, 19),
        procurement_repos,
    )
    po = purchase_order_repo.get_purchase_order("PO-0001")
    after = inventory_repo.get_inventory_for_sku("TOTE")

    assert result.status == "partial"
    assert po is not None
    assert po["purchase_order"]["status"] == "partial"
    assert po["lines"][0]["quantity_received"] == 40
    assert after["on_hand_qty"] == before["on_hand_qty"] + 40

