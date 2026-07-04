"""Database bootstrap and seed loading."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from retail_agent.db.schema import create_schema, schema_version


SEED_FILES = {
    "products": "products.csv",
    "customers": "customers.csv",
    "suppliers": "suppliers.csv",
    "supplier_catalog": "supplier_catalog.csv",
    "inventory": "inventory.csv",
    "orders": "orders.csv",
    "order_lines": "order_lines.csv",
    "returns": "returns.csv",
    "promotions": "promotions.csv",
}


def bootstrap_database(conn: sqlite3.Connection, seed_data_dir: Path) -> bool:
    """Initialize schema and seed data if the database is not ready."""
    create_schema(conn)

    if is_seeded(conn):
        return False

    if has_existing_seed_data(conn):
        mark_seeded(conn)
        conn.commit()
        return False

    load_seed_csvs(conn, seed_data_dir)
    mark_seeded(conn)
    conn.commit()
    return True


def database_exists(db_path: Path) -> bool:
    """Return True when the SQLite database file exists on disk."""
    return db_path.exists()


def is_seeded(conn: sqlite3.Connection) -> bool:
    """Return True when the database has already been seeded."""
    row = conn.execute(
        "SELECT value FROM schema_metadata WHERE key = 'seeded_at_schema_version'"
    ).fetchone()
    return bool(row and row["value"] == schema_version())


def has_existing_seed_data(conn: sqlite3.Connection) -> bool:
    """Return True when core seeded tables already contain data."""
    row = conn.execute("SELECT COUNT(*) AS count FROM products").fetchone()
    return bool(row and row["count"] > 0)


def load_seed_csvs(conn: sqlite3.Connection, seed_data_dir: Path) -> None:
    """Load CSV seed data into the SQLite database."""
    for table_name, file_name in SEED_FILES.items():
        load_csv_into_table(conn, table_name, seed_data_dir / file_name)


def load_csv_into_table(
    conn: sqlite3.Connection,
    table_name: str,
    csv_path: Path,
) -> None:
    """Insert every row from a CSV file into its matching table."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        return

    columns = reader.fieldnames or []
    placeholders = ", ".join(["?"] * len(columns))
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
    values = [tuple(_normalize_csv_value(row[column]) for column in columns) for row in rows]
    conn.executemany(sql, values)


def mark_seeded(conn: sqlite3.Connection) -> None:
    """Persist the schema version used for seed bootstrap."""
    conn.execute(
        """
        INSERT INTO schema_metadata(key, value)
        VALUES ('seeded_at_schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (schema_version(),),
    )


def _normalize_csv_value(value: str | None) -> str | None:
    if value == "":
        return None
    return value
