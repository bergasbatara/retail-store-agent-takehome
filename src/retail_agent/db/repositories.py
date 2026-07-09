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

    def list_skus_for_product(self, product_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM skus
            WHERE product_id = ?
            ORDER BY color, size, sku
            """,
            (product_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    def list_categories(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM skus ORDER BY category"
        ).fetchall()
        return [str(row["category"]) for row in rows]

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

    def adjust_on_hand(self, sku: str, delta: int, *, commit: bool = True) -> None:
        self.conn.execute(
            "UPDATE inventory SET on_hand_qty = on_hand_qty + ? WHERE sku = ?",
            (delta, sku),
        )
        if commit:
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

    def list_inventory_for_product(self, product_id: str) -> list[dict[str, Any]]:
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
            WHERE p.product_id = ?
            ORDER BY p.color, p.size, i.sku
            """,
            (product_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    def list_all_inventory(self) -> list[dict[str, Any]]:
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
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO orders(order_id, order_date, customer_id, order_discount_pct, payment_method)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, order_date, customer_id, order_discount_pct, payment_method),
        )
        if commit:
            self.conn.commit()

    def add_order_line(
        self,
        order_id: str,
        line_no: int,
        sku: str,
        quantity: int,
        unit_price: str,
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO order_lines(order_id, line_no, sku, quantity, unit_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, line_no, sku, quantity, unit_price),
        )
        if commit:
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

    def find_orders(self, query: str) -> list[dict[str, Any]]:
        like_query = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT DISTINCT
                o.order_id,
                o.order_date,
                o.customer_id,
                o.payment_method,
                c.name AS customer_name
            FROM orders o
            LEFT JOIN customers c ON c.customer_id = o.customer_id
            LEFT JOIN order_lines ol ON ol.order_id = o.order_id
            LEFT JOIN products p ON p.sku = ol.sku
            WHERE
                o.order_id = ?
                OR o.order_id LIKE ?
                OR lower(coalesce(c.name, '')) LIKE lower(?)
                OR lower(coalesce(p.product_name, '')) LIKE lower(?)
                OR lower(coalesce(ol.sku, '')) LIKE lower(?)
            ORDER BY o.order_date DESC, o.order_id DESC
            """,
            (query, like_query, like_query, like_query, like_query),
        ).fetchall()
        return _rows_to_dicts(rows)

    def list_units_sold_by_product(
        self,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                p.product_id,
                p.product_name,
                SUM(ol.quantity) AS units_sold
            FROM orders o
            JOIN order_lines ol ON ol.order_id = o.order_id
            JOIN products p ON p.sku = ol.sku
            WHERE o.order_date >= ? AND o.order_date <= ?
            GROUP BY p.product_id, p.product_name
            ORDER BY p.product_name
            """,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchall()
        return _rows_to_dicts(rows)

    def list_product_sales_lines(
        self,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                o.order_id,
                o.order_date,
                o.order_discount_pct,
                ol.line_no,
                ol.sku,
                ol.quantity,
                ol.unit_price,
                p.product_id,
                p.product_name
            FROM orders o
            JOIN order_lines ol ON ol.order_id = o.order_id
            JOIN products p ON p.sku = ol.sku
            WHERE o.order_date >= ? AND o.order_date <= ?
            ORDER BY o.order_date, o.order_id, ol.line_no
            """,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchall()
        return _rows_to_dicts(rows)


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
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO returns(return_id, return_date, order_id, sku, quantity, condition, refund_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (return_id, return_date, order_id, sku, quantity, condition, refund_amount),
        )
        if commit:
            self.conn.commit()

    def list_returns_for_order(self, order_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM returns WHERE order_id = ? ORDER BY return_date, return_id",
            (order_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    def list_returns_for_period(
        self,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                r.*,
                p.product_id,
                p.product_name
            FROM returns r
            JOIN products p ON p.sku = r.sku
            WHERE r.return_date >= ? AND r.return_date <= ?
            ORDER BY r.return_date, r.return_id
            """,
            (period_start.isoformat(), period_end.isoformat()),
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
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO purchase_orders(purchase_order_id, supplier_id, order_date, status)
            VALUES (?, ?, ?, ?)
            """,
            (purchase_order_id, supplier_id, order_date, status),
        )
        if commit:
            self.conn.commit()

    def add_purchase_order_line(
        self,
        purchase_order_id: str,
        line_no: int,
        sku: str,
        quantity_ordered: int,
        unit_cost: str,
        quantity_received: int = 0,
        *,
        commit: bool = True,
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
        if commit:
            self.conn.commit()

    def get_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        po_row = self.conn.execute(
            """
            SELECT po.*, s.supplier_name
            FROM purchase_orders po
            JOIN suppliers s ON s.supplier_id = po.supplier_id
            WHERE po.purchase_order_id = ?
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

    def find_purchase_orders(self, query: str) -> list[dict[str, Any]]:
        like_query = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT DISTINCT
                po.purchase_order_id,
                po.supplier_id,
                s.supplier_name,
                po.order_date,
                po.status
            FROM purchase_orders po
            JOIN suppliers s ON s.supplier_id = po.supplier_id
            LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.purchase_order_id
            LEFT JOIN products p ON p.sku = pol.sku
            WHERE
                po.purchase_order_id = ?
                OR po.purchase_order_id LIKE ?
                OR lower(s.supplier_name) LIKE lower(?)
                OR lower(coalesce(p.product_name, '')) LIKE lower(?)
                OR lower(coalesce(pol.sku, '')) LIKE lower(?)
                OR lower(po.status) LIKE lower(?)
            ORDER BY po.order_date DESC, po.purchase_order_id DESC
            """,
            (query, like_query, like_query, like_query, like_query, like_query),
        ).fetchall()
        return _rows_to_dicts(rows)

    def get_open_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        po_bundle = self.get_purchase_order(po_id)
        if po_bundle is None:
            return None
        if po_bundle["purchase_order"]["status"] == "received":
            return None
        return po_bundle

    def update_purchase_order_line_received_qty(
        self,
        purchase_order_id: str,
        sku: str,
        delta_received: int,
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE purchase_order_lines
            SET quantity_received = quantity_received + ?
            WHERE purchase_order_id = ? AND sku = ?
            """,
            (delta_received, purchase_order_id, sku),
        )
        if commit:
            self.conn.commit()

    def update_purchase_order_status(
        self,
        purchase_order_id: str,
        status: str,
        *,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            "UPDATE purchase_orders SET status = ? WHERE purchase_order_id = ?",
            (status, purchase_order_id),
        )
        if commit:
            self.conn.commit()


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
