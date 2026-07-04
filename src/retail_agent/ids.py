"""Identifier generation helpers."""

from __future__ import annotations

import sqlite3


def next_order_id(conn: sqlite3.Connection) -> str:
    """Return the next sales order ID."""
    return _next_id(conn, counter_key="orders", prefix="O-", width=4, table_name="orders", column_name="order_id")


def next_return_id(conn: sqlite3.Connection) -> str:
    """Return the next return ID."""
    return _next_id(conn, counter_key="returns", prefix="R-", width=4, table_name="returns", column_name="return_id")


def next_purchase_order_id(conn: sqlite3.Connection) -> str:
    """Return the next purchase order ID."""
    return _next_id(
        conn,
        counter_key="purchase_orders",
        prefix="PO-",
        width=4,
        table_name="purchase_orders",
        column_name="purchase_order_id",
    )


def next_promotion_id(conn: sqlite3.Connection) -> str:
    """Return the next promotion ID."""
    return _next_id(
        conn,
        counter_key="promotions",
        prefix="PR-",
        width=3,
        table_name="promotions",
        column_name="promo_id",
    )


def _next_id(
    conn: sqlite3.Connection,
    *,
    counter_key: str,
    prefix: str,
    width: int,
    table_name: str,
    column_name: str,
) -> str:
    seed_value = _load_or_initialize_counter(
        conn,
        counter_key=counter_key,
        table_name=table_name,
        column_name=column_name,
        prefix=prefix,
    )
    next_value = seed_value + 1
    conn.execute(
        """
        INSERT INTO schema_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_counter_storage_key(counter_key), str(next_value)),
    )
    conn.commit()
    return f"{prefix}{next_value:0{width}d}"


def _load_or_initialize_counter(
    conn: sqlite3.Connection,
    *,
    counter_key: str,
    table_name: str,
    column_name: str,
    prefix: str,
) -> int:
    row = conn.execute(
        "SELECT value FROM schema_metadata WHERE key = ?",
        (_counter_storage_key(counter_key),),
    ).fetchone()
    if row is not None:
        return int(row["value"])

    seeded_value = _discover_highest_numeric_suffix(
        conn,
        table_name=table_name,
        column_name=column_name,
        prefix=prefix,
    )
    conn.execute(
        """
        INSERT INTO schema_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_counter_storage_key(counter_key), str(seeded_value)),
    )
    conn.commit()
    return seeded_value


def _discover_highest_numeric_suffix(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    prefix: str,
) -> int:
    if not _table_exists(conn, table_name):
        return 0

    rows = conn.execute(f"SELECT {column_name} FROM {table_name}").fetchall()
    highest = 0
    for row in rows:
        value = row[column_name]
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        suffix = value.removeprefix(prefix)
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _counter_storage_key(counter_key: str) -> str:
    return f"id_counter:{counter_key}"
