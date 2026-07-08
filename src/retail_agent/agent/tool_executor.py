"""Tool-call dispatch for the retail agent."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from retail_agent.cli import AppContext
from retail_agent.dates import parse_date
from retail_agent.db.repositories import (
    CatalogRepository,
    CustomerRepository,
    InventoryRepository,
    OrderRepository,
    PromotionRepository,
    PurchaseOrderRepository,
    ReturnRepository,
    SupplierRepository,
)
from retail_agent.domain.catalog import resolve_product_reference, resolve_variant
from retail_agent.domain.customers import find_customer_candidates
from retail_agent.exceptions import DomainError, ValidationError
from retail_agent.money import to_decimal
from retail_agent.services.order_service import OrderRepositories, create_sale, create_walk_in_sale
from retail_agent.services.pricing_service import compute_effective_unit_price
from retail_agent.services.procurement_service import (
    ProcurementRepositories,
    create_reorder_purchase_orders,
    receive_purchase_order,
)
from retail_agent.services.promotion_service import (
    PromotionManagementRepositories,
    create_promotion,
)
from retail_agent.services.reporting_service import (
    ReportingRepositories,
    stockout_report,
    top_products_by_margin,
)
from retail_agent.services.returns_service import ReturnRepositories, process_return
from retail_agent.types import ReceiveItemInput, SaleItemInput


def execute_tool_call(name: str, arguments: dict, app_context: AppContext) -> dict:
    """Dispatch a tool call by stable name and return structured payloads."""
    handlers = {
        "ring_up_sale": handle_ring_up_sale,
        "reorder_low_stock": handle_reorder_low_stock,
        "receive_purchase_order": handle_receive_purchase_order,
        "process_return": handle_process_return,
        "create_promotion": handle_create_promotion,
        "get_product_price": handle_get_product_price,
        "top_products_by_margin": handle_top_products_by_margin,
        "stockout_risk_report": handle_stockout_risk_report,
        "find_customer": handle_find_customer,
        "find_product": handle_find_product,
    }
    handler = handlers.get(name)
    if handler is None:
        return {"ok": False, "error": {"type": "UnknownTool", "message": f"Unknown tool: {name}"}}

    try:
        payload = handler(arguments, app_context)
        return {"ok": True, "tool": name, "result": payload}
    except KeyError as exc:
        missing_key = str(exc.args[0]) if exc.args else "unknown"
        return {
            "ok": False,
            "tool": name,
            "error": {
                "type": "ValidationError",
                "message": _missing_argument_message(name, missing_key),
            },
        }
    except DomainError as exc:
        return {"ok": False, "tool": name, "error": {"type": exc.__class__.__name__, "message": str(exc)}}
    except Exception as exc:  # pragma: no cover - defensive boundary
        return {"ok": False, "tool": name, "error": {"type": exc.__class__.__name__, "message": str(exc)}}


def handle_ring_up_sale(arguments: dict, app_context: AppContext) -> dict:
    repos = _order_repositories(app_context)
    items = [_sale_item_input(item) for item in arguments["items"]]
    order_date = parse_date(arguments["order_date"])
    customer_ref = arguments.get("customer_ref")
    if customer_ref:
        result = create_sale(
            customer_ref=customer_ref,
            items=items,
            payment_method=arguments["payment_method"],
            order_date=order_date,
            repos=repos,
        )
    else:
        result = create_walk_in_sale(
            items=items,
            payment_method=arguments["payment_method"],
            order_date=order_date,
            repos=repos,
        )
    return _to_payload(result)


def handle_reorder_low_stock(arguments: dict, app_context: AppContext) -> dict:
    repos = _procurement_repositories(app_context)
    results = create_reorder_purchase_orders(parse_date(arguments["order_date"]), repos)
    return {"purchase_orders": [_to_payload(result) for result in results], "count": len(results)}


def handle_receive_purchase_order(arguments: dict, app_context: AppContext) -> dict:
    repos = _procurement_repositories(app_context)
    result = receive_purchase_order(
        po_id=arguments["purchase_order_id"],
        received_items=[
            ReceiveItemInput(
                sku=item["sku"],
                quantity_received=int(item["quantity_received"]),
            )
            for item in arguments["received_items"]
        ],
        receive_date=parse_date(arguments["receive_date"]),
        repos=repos,
    )
    return _to_payload(result)


def handle_process_return(arguments: dict, app_context: AppContext) -> dict:
    repos = _return_repositories(app_context)
    result = process_return(
        order_id=arguments["order_id"],
        sku_or_ref=arguments["sku_or_ref"],
        quantity=int(arguments["quantity"]),
        condition=arguments["condition"],
        return_date=parse_date(arguments["return_date"]),
        repos=repos,
    )
    return _to_payload(result)


def handle_create_promotion(arguments: dict, app_context: AppContext) -> dict:
    repos = _promotion_repositories(app_context)
    result = create_promotion(
        scope_type=arguments["scope_type"],
        scope_ref=arguments["scope_ref"],
        percent_off=to_decimal(arguments["percent_off"]),
        start_date=parse_date(arguments["start_date"]),
        end_date=parse_date(arguments["end_date"]),
        description=arguments["description"],
        repos=repos,
    )
    return _to_payload(result)


def handle_get_product_price(arguments: dict, app_context: AppContext) -> dict:
    catalog = CatalogRepository(app_context.conn)
    promotions = PromotionRepository(app_context.conn)
    sale_date = parse_date(arguments["sale_date"])
    price = compute_effective_unit_price(
        sku=arguments["sku"],
        sale_date=sale_date,
        promo_repo=promotions,
        catalog_repo=catalog,
    )
    return {"sku": arguments["sku"], "sale_date": sale_date.isoformat(), "effective_unit_price": str(price)}


def handle_top_products_by_margin(arguments: dict, app_context: AppContext) -> dict:
    repos = _reporting_repositories(app_context)
    rows = top_products_by_margin(
        limit=int(arguments["limit"]),
        period_start=parse_date(arguments["period_start"]),
        period_end=parse_date(arguments["period_end"]),
        repos=repos,
    )
    return {"rows": [_to_payload(row) for row in rows], "count": len(rows)}


def handle_stockout_risk_report(arguments: dict, app_context: AppContext) -> dict:
    repos = _reporting_repositories(app_context)
    rows = stockout_report(parse_date(arguments["as_of_date"]), repos)
    return {"rows": [_to_payload(row) for row in rows], "count": len(rows)}


def handle_find_customer(arguments: dict, app_context: AppContext) -> dict:
    repo = CustomerRepository(app_context.conn)
    customers = find_customer_candidates(arguments["query"], repo)
    return {"customers": [_to_payload(customer) for customer in customers], "count": len(customers)}


def handle_find_product(arguments: dict, app_context: AppContext) -> dict:
    repo = CatalogRepository(app_context.conn)
    color = arguments.get("color")
    size = arguments.get("size")
    if color is not None or size is not None:
        result = resolve_variant(arguments["query"], color, size, repo)
        return {"product": _to_payload(result)}
    result = resolve_product_reference(arguments["query"], repo)
    return {"product": _to_payload(result)}


def _order_repositories(app_context: AppContext) -> OrderRepositories:
    conn = app_context.conn
    return OrderRepositories(
        catalog=CatalogRepository(conn),
        customers=CustomerRepository(conn),
        inventory=InventoryRepository(conn),
        orders=OrderRepository(conn),
        promotions=PromotionRepository(conn),
    )


def _procurement_repositories(app_context: AppContext) -> ProcurementRepositories:
    conn = app_context.conn
    return ProcurementRepositories(
        catalog=CatalogRepository(conn),
        inventory=InventoryRepository(conn),
        purchase_orders=PurchaseOrderRepository(conn),
        suppliers=SupplierRepository(conn),
    )


def _return_repositories(app_context: AppContext) -> ReturnRepositories:
    conn = app_context.conn
    return ReturnRepositories(
        inventory=InventoryRepository(conn),
        orders=OrderRepository(conn),
        returns=ReturnRepository(conn),
    )


def _promotion_repositories(app_context: AppContext) -> PromotionManagementRepositories:
    conn = app_context.conn
    return PromotionManagementRepositories(
        catalog=CatalogRepository(conn),
        promotions=PromotionRepository(conn),
    )


def _reporting_repositories(app_context: AppContext) -> ReportingRepositories:
    conn = app_context.conn
    return ReportingRepositories(
        inventory=InventoryRepository(conn),
        orders=OrderRepository(conn),
        returns=ReturnRepository(conn),
        suppliers=SupplierRepository(conn),
    )


def _sale_item_input(raw: dict[str, Any]) -> SaleItemInput:
    return SaleItemInput(
        product_name=raw["product_name"],
        quantity=int(raw["quantity"]),
        sku=raw.get("sku"),
        color=raw.get("color"),
        size=raw.get("size"),
    )


def _missing_argument_message(tool_name: str, missing_key: str) -> str:
    specific_messages = {
        ("find_product", "query"): "Need clarification: which product should I look up?",
        ("find_customer", "query"): "Need clarification: which customer should I look up?",
        ("ring_up_sale", "items"): "Need clarification: which items should I ring up?",
        ("ring_up_sale", "payment_method"): "Need clarification: what payment method should I use?",
        ("ring_up_sale", "order_date"): "Need clarification: what sale date should I use?",
        ("ring_up_sale", "product_name"): "Need clarification: which product should I ring up?",
        ("ring_up_sale", "quantity"): "Need clarification: how many units should I ring up?",
        ("reorder_low_stock", "order_date"): "Need clarification: what reorder date should I use?",
        ("receive_purchase_order", "purchase_order_id"): "Need clarification: which purchase order should I receive?",
        ("receive_purchase_order", "receive_date"): "Need clarification: what receipt date should I use?",
        ("receive_purchase_order", "received_items"): "Need clarification: which received items should I record?",
        ("process_return", "order_id"): "Need clarification: which order is being returned?",
        ("process_return", "sku_or_ref"): "Need clarification: which item from the order is being returned?",
        ("process_return", "quantity"): "Need clarification: how many units are being returned?",
        ("process_return", "condition"): "Need clarification: is the return in good or damaged condition?",
        ("process_return", "return_date"): "Need clarification: what return date should I use?",
        ("create_promotion", "scope_type"): "Need clarification: is the promotion for a product or a category?",
        ("create_promotion", "scope_ref"): "Need clarification: which product or category should the promotion target?",
        ("create_promotion", "percent_off"): "Need clarification: what percent discount should I apply?",
        ("create_promotion", "start_date"): "Need clarification: what promotion start date should I use?",
        ("create_promotion", "end_date"): "Need clarification: what promotion end date should I use?",
        ("create_promotion", "description"): "Need clarification: how should I describe the promotion?",
        ("get_product_price", "sku"): "Need clarification: which SKU should I price?",
        ("get_product_price", "sale_date"): "Need clarification: what sale date should I price for?",
        ("top_products_by_margin", "limit"): "Need clarification: how many products should I return?",
        ("top_products_by_margin", "period_start"): "Need clarification: what margin report start date should I use?",
        ("top_products_by_margin", "period_end"): "Need clarification: what margin report end date should I use?",
        ("stockout_risk_report", "as_of_date"): "Need clarification: what stockout report date should I use?",
    }
    return specific_messages.get(
        (tool_name, missing_key),
        f"Missing required argument '{missing_key}' for tool '{tool_name}'.",
    )


def _to_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_to_payload(item) for item in value]
    if isinstance(value, list):
        return [_to_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_payload(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_payload(item) for key, item in asdict(value).items()}
    return value
