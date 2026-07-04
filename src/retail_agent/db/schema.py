"""Database schema creation."""

from __future__ import annotations

import sqlite3


SCHEMA_VERSION = "2"


def schema_version() -> str:
    """Return the current application schema version."""
    return SCHEMA_VERSION


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

        CREATE TABLE IF NOT EXISTS purchase_orders (
            purchase_order_id TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
        );

        CREATE TABLE IF NOT EXISTS purchase_order_lines (
            purchase_order_id TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity_ordered INTEGER NOT NULL,
            quantity_received INTEGER NOT NULL DEFAULT 0,
            unit_cost TEXT NOT NULL,
            PRIMARY KEY (purchase_order_id, line_no),
            FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(purchase_order_id),
            FOREIGN KEY (sku) REFERENCES products(sku)
        );

        CREATE TABLE IF NOT EXISTS session_memory (
            session_id TEXT PRIMARY KEY,
            memory_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_products_product_id ON products(product_id);
        CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
        CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
        CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);
        CREATE INDEX IF NOT EXISTS idx_order_lines_sku ON order_lines(sku);
        CREATE INDEX IF NOT EXISTS idx_returns_order_id ON returns(order_id);
        CREATE INDEX IF NOT EXISTS idx_returns_sku ON returns(sku);
        CREATE INDEX IF NOT EXISTS idx_promotions_date_window ON promotions(start_date, end_date);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier_id ON purchase_orders(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_order_lines_sku ON purchase_order_lines(sku);

        CREATE VIEW IF NOT EXISTS skus AS
        SELECT
            sku,
            product_id,
            product_name,
            category,
            color,
            size,
            retail_price
        FROM products;

        CREATE VIEW IF NOT EXISTS supplier_offers AS
        SELECT
            supplier_id,
            product_id,
            unit_cost,
            lead_time_days
        FROM supplier_catalog;
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
