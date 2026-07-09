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
from retail_agent.domain.catalog import candidate_reference_terms, resolve_product_reference, resolve_variant
from retail_agent.domain.customers import find_customer_candidates
from retail_agent.domain.resolution import resolve_return_target
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
        "find_order": handle_find_order,
        "find_purchase_order": handle_find_purchase_order,
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
    po_bundle = repos.purchase_orders.get_open_purchase_order(arguments["purchase_order_id"])
    if po_bundle is None:
        raise ValidationError(
            f"Open purchase order '{arguments['purchase_order_id']}' was not found. Use find_purchase_order first if you need to resolve the PO ID."
        )
    result = receive_purchase_order(
        po_id=arguments["purchase_order_id"],
        received_items=[
            _receive_item_input(item, po_bundle["lines"])
            for item in arguments["received_items"]
        ],
        receive_date=parse_date(arguments["receive_date"]),
        repos=repos,
    )
    return _to_payload(result)


def handle_process_return(arguments: dict, app_context: AppContext) -> dict:
    repos = _return_repositories(app_context)
    order_bundle = repos.orders.get_order_with_lines(arguments["order_id"])
    if order_bundle is None:
        raise ValidationError(
            f"Order '{arguments['order_id']}' was not found. Use find_order first if you need to resolve the order ID."
        )
    resolved_item = resolve_return_target(
        arguments["order_id"],
        arguments["sku_or_ref"],
        repos.orders,
    )
    result = process_return(
        order_id=arguments["order_id"],
        sku_or_ref=resolved_item.sku,
        quantity=int(arguments["quantity"]),
        condition=arguments["condition"],
        return_date=parse_date(arguments["return_date"]),
        repos=repos,
    )
    return _to_payload(result)


def handle_create_promotion(arguments: dict, app_context: AppContext) -> dict:
    repos = _promotion_repositories(app_context)
    scope_ref = _resolve_promotion_scope_ref(arguments, repos.catalog)
    result = create_promotion(
        scope_type=arguments["scope_type"],
        scope_ref=scope_ref,
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
    sku = _resolve_price_lookup_sku(arguments, catalog)
    price = compute_effective_unit_price(
        sku=sku,
        sale_date=sale_date,
        promo_repo=promotions,
        catalog_repo=catalog,
    )
    return {"sku": sku, "sale_date": sale_date.isoformat(), "effective_unit_price": str(price)}


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


def handle_find_order(arguments: dict, app_context: AppContext) -> dict:
    repo = OrderRepository(app_context.conn)
    query = str(arguments["query"]).strip()
    exact_bundle = repo.get_order_with_lines(query)
    if exact_bundle is not None:
        return {"order": _to_payload(exact_bundle)}
    orders = repo.find_orders(query)
    return {"orders": [_to_payload(order) for order in orders], "count": len(orders)}


def handle_find_purchase_order(arguments: dict, app_context: AppContext) -> dict:
    repo = PurchaseOrderRepository(app_context.conn)
    query = str(arguments["query"]).strip()
    exact_bundle = repo.get_purchase_order(query)
    if exact_bundle is not None:
        return {"purchase_order": _to_payload(exact_bundle)}
    orders = repo.find_purchase_orders(query)
    return {"purchase_orders": [_to_payload(order) for order in orders], "count": len(orders)}


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


def _receive_item_input(raw: dict[str, Any], po_lines: list[dict[str, Any]]) -> ReceiveItemInput:
    sku = _optional_non_empty_str(raw.get("sku"))
    if sku:
        return ReceiveItemInput(
            sku=sku,
            quantity_received=int(raw["quantity_received"]),
        )

    product_name = _optional_non_empty_str(raw.get("product_name"))
    if not product_name:
        raise ValidationError(
            "Need clarification: which purchase-order line should I receive? Provide the exact SKU or product name from find_purchase_order."
        )

    matched_sku = _resolve_po_line_sku(product_name, po_lines)
    return ReceiveItemInput(
        sku=matched_sku,
        quantity_received=int(raw["quantity_received"]),
    )


def _resolve_po_line_sku(reference: str, po_lines: list[dict[str, Any]]) -> str:
    for candidate in candidate_reference_terms(reference):
        normalized_reference = candidate.lower()
        exact_sku_matches = [line for line in po_lines if str(line["sku"]).lower() == normalized_reference]
        if len(exact_sku_matches) == 1:
            return str(exact_sku_matches[0]["sku"])

        fuzzy_matches = [
            line
            for line in po_lines
            if normalized_reference in str(line.get("product_name", "")).lower()
            or normalized_reference in _po_line_descriptor(line).lower()
        ]
        if len(fuzzy_matches) == 1:
            return str(fuzzy_matches[0]["sku"])
        if len(fuzzy_matches) > 1:
            options = ", ".join(_po_line_descriptor(line) for line in fuzzy_matches)
            raise ValidationError(
                f"Multiple purchase-order lines match '{reference}'. Which one did you want? Options: {options}."
            )

    raise ValidationError(
        f"No purchase-order line matches '{reference}'. Use find_purchase_order first to inspect the PO lines."
    )


def _po_line_descriptor(line: dict[str, Any]) -> str:
    parts = [str(line.get("product_name", ""))]
    if line.get("color"):
        parts.append(str(line["color"]))
    if line.get("size"):
        parts.append(str(line["size"]))
    parts.append(f"[{line['sku']}]")
    return " ".join(part for part in parts if part)


def _resolve_promotion_scope_ref(arguments: dict[str, Any], catalog_repo: CatalogRepository) -> str:
    scope_type = str(arguments["scope_type"])
    scope_ref = str(arguments["scope_ref"]).strip()
    if scope_type != "product":
        return scope_ref
    if scope_ref.startswith("P-"):
        return scope_ref
    resolution = resolve_product_reference(scope_ref, catalog_repo)
    return resolution.product_id


def _resolve_price_lookup_sku(arguments: dict[str, Any], catalog_repo: CatalogRepository) -> str:
    sku = _optional_non_empty_str(arguments.get("sku"))
    if sku:
        return sku

    query = _optional_non_empty_str(arguments.get("query"))
    if not query:
        raise ValidationError(
            "Need clarification: which product should I price? Use find_product first or provide a product query."
        )
    resolved = resolve_variant(query, arguments.get("color"), arguments.get("size"), catalog_repo)
    return resolved.sku


def _optional_non_empty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _missing_argument_message(tool_name: str, missing_key: str) -> str:
    specific_messages = {
        ("find_product", "query"): "Need clarification: which product should I look up?",
        ("find_customer", "query"): "Need clarification: which customer should I look up?",
        ("find_order", "query"): "Need clarification: which order should I look up?",
        ("find_purchase_order", "query"): "Need clarification: which purchase order should I look up?",
        ("ring_up_sale", "items"): "Need clarification: which items should I ring up?",
        ("ring_up_sale", "payment_method"): "Need clarification: what payment method should I use?",
        ("ring_up_sale", "order_date"): "Need clarification: what sale date should I use?",
        ("ring_up_sale", "product_name"): "Need clarification: which product should I ring up?",
        ("ring_up_sale", "quantity"): "Need clarification: how many units should I ring up?",
        ("reorder_low_stock", "order_date"): "Need clarification: what reorder date should I use?",
        ("receive_purchase_order", "purchase_order_id"): "Need clarification: which purchase order should I receive?",
        ("receive_purchase_order", "receive_date"): "Need clarification: what receipt date should I use?",
        ("receive_purchase_order", "received_items"): "Need clarification: which received items should I record?",
        ("receive_purchase_order", "quantity_received"): "Need clarification: how many units were received for that PO line?",
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
        ("get_product_price", "query"): "Need clarification: which product should I price?",
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
