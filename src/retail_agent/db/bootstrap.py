"""Database bootstrap and seed loading."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from retail_agent.db.schema import create_schema, schema_version
from retail_agent.ingest.csv_loader import load_all_seed_files
from retail_agent.types import SeedDataBundle


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
    bundle = load_all_seed_files(seed_data_dir)
    load_seed_bundle(conn, bundle)


def load_seed_bundle(conn: sqlite3.Connection, bundle: SeedDataBundle) -> None:
    """Insert a normalized seed bundle into the database."""
    for table_name, rows in (
        ("products", bundle.products),
        ("customers", bundle.customers),
        ("suppliers", bundle.suppliers),
        ("supplier_catalog", bundle.supplier_catalog),
        ("inventory", bundle.inventory),
        ("orders", bundle.orders),
        ("order_lines", bundle.order_lines),
        ("returns", bundle.returns),
        ("promotions", bundle.promotions),
    ):
        load_table_rows(conn, table_name, rows)


def load_table_rows(conn: sqlite3.Connection, table_name: str, rows: tuple[dict, ...]) -> None:
    """Insert normalized rows into a target table."""
    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
    values = [tuple(_normalize_sql_value(row[column]) for column in columns) for row in rows]
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


def _normalize_sql_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
