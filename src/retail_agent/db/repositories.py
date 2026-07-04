"""Thin repository layer over the SQLite schema."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


@dataclass
class CatalogRepository:
    conn: sqlite3.Connection

    def get_sku(self, sku: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM skus WHERE sku = ?", (sku,)).fetchone()
        return _row_to_dict(row)

    def find_skus_by_product_name(self, name: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM skus
            WHERE lower(product_name) = lower(?)
            ORDER BY color, size, sku
            """,
            (name,),
        ).fetchall()
        return _rows_to_dicts(rows)

    def find_matching_variant(
        self,
        product_name: str,
        color: str | None,
        size: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["lower(product_name) = lower(?)"]
        params: list[Any] = [product_name]
        if color is not None:
            clauses.append("lower(color) = lower(?)")
            params.append(color)
        if size is not None:
            clauses.append("lower(size) = lower(?)")
            params.append(size)
        query = f"""
            SELECT * FROM skus
            WHERE {' AND '.join(clauses)}
            ORDER BY color, size, sku
        """
        rows = self.conn.execute(query, tuple(params)).fetchall()
        return _rows_to_dicts(rows)


@dataclass
class CustomerRepository:
    conn: sqlite3.Connection

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        return _row_to_dict(row)

    def find_by_name_or_email(self, query: str) -> list[dict[str, Any]]:
        like_query = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT * FROM customers
            WHERE lower(name) LIKE lower(?) OR lower(email) LIKE lower(?)
            ORDER BY name
            """,
            (like_query, like_query),
        ).fetchall()
        return _rows_to_dicts(rows)


@dataclass
class InventoryRepository:
    conn: sqlite3.Connection

    def get_inventory_for_sku(self, sku: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT i.*, p.product_id, p.product_name, p.category, p.color, p.size
            FROM inventory i
            JOIN products p ON p.sku = i.sku
            WHERE i.sku = ?
            """,
            (sku,),
        ).fetchone()
        return _row_to_dict(row)

    def adjust_on_hand(self, sku: str, delta: int) -> None:
        self.conn.execute(
            "UPDATE inventory SET on_hand_qty = on_hand_qty + ? WHERE sku = ?",
            (delta, sku),
        )
        self.conn.commit()

    def list_reorder_candidates(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                i.*,
                p.product_id,
                p.product_name,
                p.category,
                p.color,
                p.size
            FROM inventory i
            JOIN products p ON p.sku = i.sku
            WHERE i.on_hand_qty <= i.reorder_point
            ORDER BY p.product_name, p.color, p.size, i.sku
            """
        ).fetchall()
        return _rows_to_dicts(rows)


@dataclass
class OrderRepository:
    conn: sqlite3.Connection

    def create_order(
        self,
        order_id: str,
        order_date: str,
        customer_id: str | None,
        order_discount_pct: str,
        payment_method: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO orders(order_id, order_date, customer_id, order_discount_pct, payment_method)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, order_date, customer_id, order_discount_pct, payment_method),
        )
        self.conn.commit()

    def add_order_line(
        self,
        order_id: str,
        line_no: int,
        sku: str,
        quantity: int,
        unit_price: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO order_lines(order_id, line_no, sku, quantity, unit_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, line_no, sku, quantity, unit_price),
        )
        self.conn.commit()

    def get_order_with_lines(self, order_id: str) -> dict[str, Any] | None:
        order_row = self.conn.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if order_row is None:
            return None

        line_rows = self.conn.execute(
            """
            SELECT
                ol.*,
                p.product_id,
                p.product_name,
                p.category,
                p.color,
                p.size
            FROM order_lines ol
            JOIN products p ON p.sku = ol.sku
            WHERE ol.order_id = ?
            ORDER BY ol.line_no
            """,
            (order_id,),
        ).fetchall()
        return {
            "order": dict(order_row),
            "lines": _rows_to_dicts(line_rows),
        }


@dataclass
class ReturnRepository:
    conn: sqlite3.Connection

    def create_return(
        self,
        return_id: str,
        return_date: str,
        order_id: str,
        sku: str,
        quantity: int,
        condition: str,
        refund_amount: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO returns(return_id, return_date, order_id, sku, quantity, condition, refund_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (return_id, return_date, order_id, sku, quantity, condition, refund_amount),
        )
        self.conn.commit()

    def list_returns_for_order(self, order_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM returns WHERE order_id = ? ORDER BY return_date, return_id",
            (order_id,),
        ).fetchall()
        return _rows_to_dicts(rows)


@dataclass
class SupplierRepository:
    conn: sqlite3.Connection

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM suppliers WHERE supplier_id = ?",
            (supplier_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_supplier_offers(self, product_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT so.*, s.supplier_name
            FROM supplier_offers so
            JOIN suppliers s ON s.supplier_id = so.supplier_id
            WHERE so.product_id = ?
            ORDER BY unit_cost, lead_time_days, so.supplier_id
            """,
            (product_id,),
        ).fetchall()
        return _rows_to_dicts(rows)


@dataclass
class PromotionRepository:
    conn: sqlite3.Connection

    def list_active_promotions(self, target_date: date) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM promotions
            WHERE start_date <= ? AND end_date >= ?
            ORDER BY start_date, end_date, promo_id
            """,
            (target_date.isoformat(), target_date.isoformat()),
        ).fetchall()
        return _rows_to_dicts(rows)

    def create_promotion(
        self,
        promo_id: str,
        description: str,
        promo_type: str,
        value: str,
        scope_type: str,
        scope_ref: str,
        start_date: str,
        end_date: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO promotions(
                promo_id, description, type, value, scope_type, scope_ref, start_date, end_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (promo_id, description, promo_type, value, scope_type, scope_ref, start_date, end_date),
        )
        self.conn.commit()


@dataclass
class PurchaseOrderRepository:
    conn: sqlite3.Connection

    def create_purchase_order(
        self,
        purchase_order_id: str,
        supplier_id: str,
        order_date: str,
        status: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO purchase_orders(purchase_order_id, supplier_id, order_date, status)
            VALUES (?, ?, ?, ?)
            """,
            (purchase_order_id, supplier_id, order_date, status),
        )
        self.conn.commit()

    def add_purchase_order_line(
        self,
        purchase_order_id: str,
        line_no: int,
        sku: str,
        quantity_ordered: int,
        unit_cost: str,
        quantity_received: int = 0,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO purchase_order_lines(
                purchase_order_id, line_no, sku, quantity_ordered, quantity_received, unit_cost
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (purchase_order_id, line_no, sku, quantity_ordered, quantity_received, unit_cost),
        )
        self.conn.commit()

    def get_open_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        po_row = self.conn.execute(
            """
            SELECT po.*, s.supplier_name
            FROM purchase_orders po
            JOIN suppliers s ON s.supplier_id = po.supplier_id
            WHERE po.purchase_order_id = ? AND po.status != 'received'
            """,
            (po_id,),
        ).fetchone()
        if po_row is None:
            return None

        line_rows = self.conn.execute(
            """
            SELECT pol.*, p.product_id, p.product_name, p.color, p.size
            FROM purchase_order_lines pol
            JOIN products p ON p.sku = pol.sku
            WHERE pol.purchase_order_id = ?
            ORDER BY pol.line_no
            """,
            (po_id,),
        ).fetchall()
        return {
            "purchase_order": dict(po_row),
            "lines": _rows_to_dicts(line_rows),
        }


@dataclass
class SessionRepository:
    conn: sqlite3.Connection

    def get_memory(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT memory_json FROM session_memory WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["memory_json"])

    def save_memory(self, session_id: str, memory: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO session_memory(session_id, memory_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id)
            DO UPDATE SET
                memory_json = excluded.memory_json,
                updated_at = excluded.updated_at
            """,
            (session_id, json.dumps(memory, sort_keys=True), datetime.utcnow().isoformat()),
        )
        self.conn.commit()
