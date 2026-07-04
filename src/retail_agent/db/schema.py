"""Database schema creation."""

from __future__ import annotations

import sqlite3


SCHEMA_VERSION = "1"


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the initial application schema."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            color TEXT,
            size TEXT,
            retail_price TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            joined_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            supplier_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS supplier_catalog (
            supplier_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            unit_cost TEXT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            PRIMARY KEY (supplier_id, product_id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        );

        CREATE TABLE IF NOT EXISTS inventory (
            sku TEXT PRIMARY KEY,
            on_hand_qty INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            reorder_qty INTEGER NOT NULL,
            FOREIGN KEY (sku) REFERENCES products(sku)
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            order_date TEXT NOT NULL,
            customer_id TEXT,
            order_discount_pct TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS order_lines (
            order_id TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price TEXT NOT NULL,
            PRIMARY KEY (order_id, line_no),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (sku) REFERENCES products(sku)
        );

        CREATE TABLE IF NOT EXISTS returns (
            return_id TEXT PRIMARY KEY,
            return_date TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            condition TEXT NOT NULL,
            refund_amount TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (sku) REFERENCES products(sku)
        );

        CREATE TABLE IF NOT EXISTS promotions (
            promo_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_ref TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO schema_metadata(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SCHEMA_VERSION,),
    )
    conn.commit()
