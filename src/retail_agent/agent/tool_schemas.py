"""Tool definitions exposed to the chat runtime."""

from __future__ import annotations


def build_tool_definitions() -> list[dict]:
    """Return stable JSON tool schemas for the retail agent."""
    return [
        _ring_up_sale_schema(),
        _reorder_low_stock_schema(),
        _receive_purchase_order_schema(),
        _process_return_schema(),
        _create_promotion_schema(),
        _get_product_price_schema(),
        _top_products_by_margin_schema(),
        _stockout_risk_report_schema(),
        _find_customer_schema(),
        _find_product_schema(),
        _find_order_schema(),
        _find_purchase_order_schema(),
    ]


def _ring_up_sale_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "ring_up_sale",
            "description": "Create a sale for a walk-in or known customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_ref": {"type": ["string", "null"]},
                    "payment_method": {"type": "string", "enum": ["cash", "card"]},
                    "order_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1},
                                "sku": {"type": ["string", "null"]},
                                "color": {"type": ["string", "null"]},
                                "size": {"type": ["string", "null"]},
                            },
                            "required": ["product_name", "quantity"],
                            "additionalProperties": False,
                        },
                        "minItems": 1,
                    },
                },
                "required": ["payment_method", "order_date", "items"],
                "additionalProperties": False,
            },
        },
    }


def _reorder_low_stock_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "reorder_low_stock",
            "description": "Create purchase orders for SKUs at or below reorder point.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["order_date"],
                "additionalProperties": False,
            },
        },
    }


def _receive_purchase_order_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "receive_purchase_order",
            "description": "Receive some or all quantities on an open purchase order. Use find_purchase_order first unless you already have the exact purchase_order_id and PO line SKU from a tool result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purchase_order_id": {"type": "string"},
                    "receive_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "received_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": ["string", "null"]},
                                "product_name": {"type": ["string", "null"]},
                                "quantity_received": {"type": "integer", "minimum": 1},
                            },
                            "required": ["quantity_received"],
                            "additionalProperties": False,
                        },
                        "minItems": 1,
                    },
                },
                "required": ["purchase_order_id", "receive_date", "received_items"],
                "additionalProperties": False,
            },
        },
    }


def _process_return_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "process_return",
            "description": "Process a return against an existing order. Use find_order first unless you already have the exact order_id and sold item reference from a tool result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "sku_or_ref": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                    "condition": {"type": "string", "enum": ["good", "damaged"]},
                    "return_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["order_id", "sku_or_ref", "quantity", "condition", "return_date"],
                "additionalProperties": False,
            },
        },
    }


def _create_promotion_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "create_promotion",
            "description": "Create a percent-off promotion for a product or category. If targeting a product and you do not already have its exact product_id from a lookup, use find_product first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope_type": {"type": "string", "enum": ["product", "category"]},
                    "scope_ref": {"type": "string"},
                    "percent_off": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 100},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "description": {"type": "string"},
                },
                "required": ["scope_type", "scope_ref", "percent_off", "start_date", "end_date", "description"],
                "additionalProperties": False,
            },
        },
    }


def _get_product_price_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "get_product_price",
            "description": "Get the effective sale price for a concrete SKU on a given date. Use find_product first unless you already have the exact SKU from a tool result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": ["string", "null"]},
                    "query": {"type": ["string", "null"]},
                    "color": {"type": ["string", "null"]},
                    "size": {"type": ["string", "null"]},
                    "sale_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["sale_date"],
                "additionalProperties": False,
            },
        },
    }


def _top_products_by_margin_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "top_products_by_margin",
            "description": "Rank products by margin for a time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1},
                    "period_start": {"type": "string", "description": "YYYY-MM-DD"},
                    "period_end": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["limit", "period_start", "period_end"],
                "additionalProperties": False,
            },
        },
    }


def _stockout_risk_report_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "stockout_risk_report",
            "description": "Report products that are below reorder point or low on days of cover.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["as_of_date"],
                "additionalProperties": False,
            },
        },
    }


def _find_customer_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "find_customer",
            "description": "Find customers by ID, name, or email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _find_product_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "find_product",
            "description": "Find a product or concrete variant by SKU or product description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "color": {"type": ["string", "null"]},
                    "size": {"type": ["string", "null"]},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _find_order_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "find_order",
            "description": "Find an order by order ID, customer name, sold SKU, or sold product name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _find_purchase_order_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "find_purchase_order",
            "description": "Find a purchase order by purchase-order ID, supplier name, SKU, product name, or status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }
