"""Seed CSV loading and normalization."""

from __future__ import annotations

import csv
from pathlib import Path

from retail_agent.ingest.mappers import (
    map_customer_row,
    map_inventory_row,
    map_order_line_row,
    map_order_row,
    map_product_row,
    map_promotion_row,
    map_return_row,
    map_supplier_offer_row,
    map_supplier_row,
)
from retail_agent.ingest.validators import validate_seed_bundle
from retail_agent.types import SeedDataBundle


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read raw rows from a CSV file."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def load_all_seed_files(seed_data_dir: str | Path) -> SeedDataBundle:
    """Load, normalize, and validate the full seed dataset."""
    base_dir = Path(seed_data_dir)
    bundle = SeedDataBundle(
        products=tuple(map(map_product_row, read_csv_rows(base_dir / "products.csv"))),
        customers=tuple(map(map_customer_row, read_csv_rows(base_dir / "customers.csv"))),
        suppliers=tuple(map(map_supplier_row, read_csv_rows(base_dir / "suppliers.csv"))),
        supplier_catalog=tuple(
            map(map_supplier_offer_row, read_csv_rows(base_dir / "supplier_catalog.csv"))
        ),
        inventory=tuple(map(map_inventory_row, read_csv_rows(base_dir / "inventory.csv"))),
        orders=tuple(map(map_order_row, read_csv_rows(base_dir / "orders.csv"))),
        order_lines=tuple(map(map_order_line_row, read_csv_rows(base_dir / "order_lines.csv"))),
        returns=tuple(map(map_return_row, read_csv_rows(base_dir / "returns.csv"))),
        promotions=tuple(map(map_promotion_row, read_csv_rows(base_dir / "promotions.csv"))),
    )
    validate_seed_bundle(bundle)
    return bundle
