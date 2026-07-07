from __future__ import annotations

from datetime import date

from retail_agent.services.order_service import create_sale, create_walk_in_sale
from retail_agent.types import SaleItemInput


def test_walk_in_sale_decrements_inventory(order_repos, inventory_repo):
    before = inventory_repo.get_inventory_for_sku("TOTE")
    result = create_walk_in_sale(
        items=[SaleItemInput(product_name="Canvas Tote", quantity=2)],
        payment_method="cash",
        order_date=date(2026, 6, 19),
        repos=order_repos,
    )
    after = inventory_repo.get_inventory_for_sku("TOTE")

    assert result.customer_id is None
    assert result.order_id.startswith("O-")
    assert after["on_hand_qty"] == before["on_hand_qty"] - 2


def test_named_customer_sale_persists_order_and_lines(order_repos):
    result = create_sale(
        customer_ref="C-001",
        items=[SaleItemInput(product_name="Canvas Tote", quantity=1)],
        payment_method="card",
        order_date=date(2026, 6, 19),
        repos=order_repos,
    )

    bundle = order_repos.orders.get_order_with_lines(result.order_id)
    assert bundle is not None
    assert bundle["order"]["customer_id"] == "C-001"
    assert bundle["order"]["payment_method"] == "card"
    assert len(bundle["lines"]) == 1
    assert bundle["lines"][0]["sku"] == "TOTE"
    assert bundle["lines"][0]["quantity"] == 1

