"""Structured session memory for follow-up reference tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from retail_agent.db.repositories import SessionRepository


@dataclass(frozen=True)
class SessionMemory:
    """Structured reference memory persisted per session."""

    last_order_id: str | None = None
    last_customer_id: str | None = None
    last_returnable_order_id: str | None = None
    last_purchase_order_id: str | None = None
    last_product_candidates: tuple[str, ...] = ()
    last_sku: str | None = None


def load_session_memory(session_id: str, repo: SessionRepository) -> SessionMemory:
    """Load structured session memory from the repository."""
    raw = repo.get_memory(session_id) or {}
    return SessionMemory(
        last_order_id=_optional_str(raw.get("last_order_id")),
        last_customer_id=_optional_str(raw.get("last_customer_id")),
        last_returnable_order_id=_optional_str(raw.get("last_returnable_order_id")),
        last_purchase_order_id=_optional_str(raw.get("last_purchase_order_id")),
        last_product_candidates=_normalize_candidates(raw.get("last_product_candidates")),
        last_sku=_optional_str(raw.get("last_sku")),
    )


def save_session_memory(
    session_id: str,
    memory: SessionMemory,
    repo: SessionRepository,
) -> None:
    """Persist structured session memory as JSON."""
    payload = asdict(memory)
    payload["last_product_candidates"] = list(memory.last_product_candidates)
    repo.save_memory(session_id, payload)


def update_memory_from_tool_result(memory: SessionMemory, result: dict) -> SessionMemory:
    """Update memory fields from a successful tool result payload."""
    if not result.get("ok"):
        return memory

    tool_name = result.get("tool")
    payload = result.get("result", {})
    updates: dict[str, Any] = {}

    if tool_name == "ring_up_sale":
        updates["last_order_id"] = payload.get("order_id") or memory.last_order_id
        updates["last_returnable_order_id"] = payload.get("order_id") or memory.last_returnable_order_id
        updates["last_customer_id"] = payload.get("customer_id") or memory.last_customer_id
        updates["last_sku"] = _extract_first_line_sku(payload) or memory.last_sku
    elif tool_name == "process_return":
        updates["last_order_id"] = payload.get("order_id") or memory.last_order_id
        updates["last_returnable_order_id"] = payload.get("order_id") or memory.last_returnable_order_id
        updates["last_sku"] = payload.get("sku") or memory.last_sku
    elif tool_name in {"reorder_low_stock", "receive_purchase_order"}:
        updates["last_purchase_order_id"] = _extract_purchase_order_id(payload) or memory.last_purchase_order_id
        updates["last_sku"] = _extract_purchase_order_sku(payload) or memory.last_sku
    elif tool_name == "find_product":
        updates["last_product_candidates"] = _extract_product_candidates(payload) or memory.last_product_candidates
        updates["last_sku"] = _extract_direct_product_sku(payload) or memory.last_sku
    elif tool_name == "find_customer":
        updates["last_customer_id"] = _extract_customer_id(payload) or memory.last_customer_id
    elif tool_name == "find_order":
        updates["last_order_id"] = _extract_order_id(payload) or memory.last_order_id
        updates["last_returnable_order_id"] = _extract_order_id(payload) or memory.last_returnable_order_id
        updates["last_sku"] = _extract_order_sku(payload) or memory.last_sku
    elif tool_name == "find_purchase_order":
        updates["last_purchase_order_id"] = _extract_purchase_order_id(payload) or memory.last_purchase_order_id
        updates["last_sku"] = _extract_purchase_order_sku(payload) or memory.last_sku
    elif tool_name == "get_product_price":
        updates["last_sku"] = payload.get("sku") or memory.last_sku
    elif tool_name == "create_promotion":
        updates["last_sku"] = payload.get("scope_ref") if payload.get("scope_type") == "sku" else memory.last_sku

    return SessionMemory(
        last_order_id=updates.get("last_order_id", memory.last_order_id),
        last_customer_id=updates.get("last_customer_id", memory.last_customer_id),
        last_returnable_order_id=updates.get(
            "last_returnable_order_id",
            memory.last_returnable_order_id,
        ),
        last_purchase_order_id=updates.get(
            "last_purchase_order_id",
            memory.last_purchase_order_id,
        ),
        last_product_candidates=tuple(
            updates.get("last_product_candidates", memory.last_product_candidates)
        ),
        last_sku=updates.get("last_sku", memory.last_sku),
    )


def inject_memory_hints(memory: SessionMemory) -> str:
    """Render compact reference hints for the current session."""
    hints: list[str] = []
    if memory.last_order_id:
        hints.append(f"Last order ID: {memory.last_order_id}")
    if memory.last_returnable_order_id:
        hints.append(f"Last returnable order ID: {memory.last_returnable_order_id}")
    if memory.last_purchase_order_id:
        hints.append(f"Last purchase order ID: {memory.last_purchase_order_id}")
    if memory.last_customer_id:
        hints.append(f"Last customer ID: {memory.last_customer_id}")
    if memory.last_sku:
        hints.append(f"Last SKU: {memory.last_sku}")
    if memory.last_product_candidates:
        hints.append(
            "Recent product candidates: "
            + ", ".join(memory.last_product_candidates)
        )
    if not hints:
        return "No prior session references."
    return "Session references:\n" + "\n".join(hints)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_candidates(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _extract_first_line_sku(payload: dict[str, Any]) -> str | None:
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        lines = receipt.get("lines") or []
        if lines:
            first = lines[0]
            if isinstance(first, dict):
                return _optional_str(first.get("sku"))
    line_items = payload.get("line_items") or []
    if line_items:
        first = line_items[0]
        if isinstance(first, dict):
            return _optional_str(first.get("sku"))
    return None


def _extract_purchase_order_id(payload: dict[str, Any]) -> str | None:
    purchase_order = payload.get("purchase_order")
    if isinstance(purchase_order, dict):
        nested_purchase_order = purchase_order.get("purchase_order")
        if isinstance(nested_purchase_order, dict):
            direct_id = _optional_str(nested_purchase_order.get("purchase_order_id"))
            if direct_id:
                return direct_id
        direct_id = _optional_str(purchase_order.get("purchase_order_id"))
        if direct_id:
            return direct_id
    if payload.get("purchase_order_id"):
        return _optional_str(payload.get("purchase_order_id"))
    orders = payload.get("purchase_orders") or []
    if orders:
        first = orders[0]
        if isinstance(first, dict):
            return _optional_str(first.get("purchase_order_id"))
    return None


def _extract_purchase_order_sku(payload: dict[str, Any]) -> str | None:
    purchase_order = payload.get("purchase_order")
    if isinstance(purchase_order, dict):
        lines = purchase_order.get("lines") or []
        if lines and isinstance(lines[0], dict):
            direct_sku = _optional_str(lines[0].get("sku"))
            if direct_sku:
                return direct_sku
    orders = payload.get("purchase_orders") or []
    if orders:
        first = orders[0]
        if isinstance(first, dict):
            message = _optional_str(first.get("message"))
            if message:
                return _extract_sku_token(message)
    message = _optional_str(payload.get("message"))
    if message:
        return _extract_sku_token(message)
    return None


def _extract_product_candidates(payload: dict[str, Any]) -> tuple[str, ...]:
    product = payload.get("product")
    if not isinstance(product, dict):
        return ()
    candidates = product.get("candidates")
    if isinstance(candidates, list):
        return tuple(
            str(candidate.get("sku"))
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("sku")
        )
    direct_sku = product.get("sku")
    if direct_sku:
        return (str(direct_sku),)
    return ()


def _extract_direct_product_sku(payload: dict[str, Any]) -> str | None:
    product = payload.get("product")
    if not isinstance(product, dict):
        return None
    return _optional_str(product.get("sku"))


def _extract_customer_id(payload: dict[str, Any]) -> str | None:
    customers = payload.get("customers") or []
    if len(customers) == 1 and isinstance(customers[0], dict):
        return _optional_str(customers[0].get("customer_id"))
    return None


def _extract_order_id(payload: dict[str, Any]) -> str | None:
    order = payload.get("order")
    if isinstance(order, dict):
        nested_order = order.get("order")
        if isinstance(nested_order, dict):
            direct_id = _optional_str(nested_order.get("order_id"))
            if direct_id:
                return direct_id
        direct_id = _optional_str(order.get("order_id"))
        if direct_id:
            return direct_id
    orders = payload.get("orders") or []
    if len(orders) == 1 and isinstance(orders[0], dict):
        return _optional_str(orders[0].get("order_id"))
    return None


def _extract_order_sku(payload: dict[str, Any]) -> str | None:
    order = payload.get("order")
    if isinstance(order, dict):
        lines = order.get("lines") or []
        if lines and isinstance(lines[0], dict):
            return _optional_str(lines[0].get("sku"))
    return None


def _extract_sku_token(message: str) -> str | None:
    for token in message.replace(".", " ").split():
        if "-" in token and token.upper() == token:
            return token
    return None
