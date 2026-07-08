from __future__ import annotations

import pytest

from retail_agent.domain.catalog import resolve_product_reference, resolve_variant
from retail_agent.domain.customers import resolve_customer
from retail_agent.exceptions import AmbiguityError


def test_ambiguous_hoodie_request_prompts_for_color_when_required(catalog_repo):
    with pytest.raises(AmbiguityError) as exc_info:
        resolve_variant("Pullover Hoodie", None, "M", catalog_repo)

    message = str(exc_info.value)
    assert "Gray" in message
    assert "Navy" in message


def test_exact_sku_and_exact_customer_matches_work(catalog_repo, customer_repo):
    product = resolve_product_reference("TEE-BLU-M", catalog_repo)
    customer = resolve_customer("C-001", customer_repo)

    assert product.candidates[0].sku == "TEE-BLU-M"
    assert customer is not None
    assert customer.customer_id == "C-001"


def test_plural_and_alias_product_names_resolve(catalog_repo):
    tote = resolve_product_reference("Canvas Totes", catalog_repo)
    tees = resolve_variant("Classic Tees", "Blue", "M", catalog_repo)
    tees_spelled_out = resolve_variant("Classic Tee", "Blue", "Medium", catalog_repo)
    hoodie = resolve_variant("hoodie", "Gray", "M", catalog_repo)

    assert tote.product_name == "Canvas Tote"
    assert tote.candidates[0].sku == "TOTE"
    assert tees.sku == "TEE-BLU-M"
    assert tees_spelled_out.sku == "TEE-BLU-M"
    assert hoodie.sku == "HOOD-GRY-M"
