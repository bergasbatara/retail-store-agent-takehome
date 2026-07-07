from __future__ import annotations

from retail_agent.db.bootstrap import bootstrap_database, database_exists
from retail_agent.db.connection import get_connection

from tests.conftest import DATA_DIR, csv_row_count


def test_database_initializes_from_csvs(tmp_path):
    db_path = tmp_path / "boot.db"

    assert not database_exists(db_path)

    conn = get_connection(db_path)
    try:
        seeded = bootstrap_database(conn, DATA_DIR)
        assert seeded is True
    finally:
        conn.close()

    assert database_exists(db_path)


def test_seeded_counts_match_files(tmp_path):
    db_path = tmp_path / "counts.db"
    conn = get_connection(db_path)
    try:
        bootstrap_database(conn, DATA_DIR)
        expected_counts = {
            "products": csv_row_count(DATA_DIR / "products.csv"),
            "customers": csv_row_count(DATA_DIR / "customers.csv"),
            "suppliers": csv_row_count(DATA_DIR / "suppliers.csv"),
            "supplier_catalog": csv_row_count(DATA_DIR / "supplier_catalog.csv"),
            "inventory": csv_row_count(DATA_DIR / "inventory.csv"),
            "orders": csv_row_count(DATA_DIR / "orders.csv"),
            "order_lines": csv_row_count(DATA_DIR / "order_lines.csv"),
            "returns": csv_row_count(DATA_DIR / "returns.csv"),
            "promotions": csv_row_count(DATA_DIR / "promotions.csv"),
        }
        for table_name, expected in expected_counts.items():
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
            assert row["count"] == expected
    finally:
        conn.close()

