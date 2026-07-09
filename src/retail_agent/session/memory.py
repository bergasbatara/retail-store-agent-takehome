"""Structured session memory for follow-up reference tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from retail_agent.db.repositories import CatalogRepository, SessionRepository
from retail_agent.domain.catalog import normalize_color, normalize_size


FOLLOW_UP_FILLER_WORDS = {
    "a",
    "an",
    "and",
    "color",
    "for",
    "is",
    "it",
    "its",
    "make",
    "one",
    "please",
    "size",
    "the",
    "to",
    "use",
    "with",
}


@dataclass(frozen=True)
class SessionMemory:
    """Structured reference memory persisted per session."""

    last_order_id: str | None = None
    last_customer_id: str | None = None
    last_returnable_order_id: str | None = None
    last_purchase_order_id: str | None = None
    last_product_candidates: tuple[str, ...] = ()
    last_sku: str | None = None


@dataclass(frozen=True)
class VariantFollowUpResolution:
    """Resolved follow-up constraint for a prior product ambiguity."""

    normalized_color: str | None
    normalized_size: str | None
    matched_skus: tuple[str, ...]
    prompt_hint: str
    updated_memory: SessionMemory


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


def resolve_variant_follow_up(
    user_text: str,
    memory: SessionMemory,
    catalog_repo: CatalogRepository,
) -> VariantFollowUpResolution | None:
    """Resolve a variant-only follow-up reply against prior product candidates."""
    if not memory.last_product_candidates:
        return None

    candidate_rows = _load_candidate_rows(memory.last_product_candidates, catalog_repo)
    if not candidate_rows:
        return None

    normalized_color, normalized_size = _parse_variant_reply(user_text, candidate_rows)
    if normalized_color is None and normalized_size is None:
        return None

    matched_rows = _filter_candidate_rows(candidate_rows, normalized_color, normalized_size)
    if not matched_rows:
        return None

    matched_skus = tuple(str(row["sku"]) for row in matched_rows)
    updated_memory = SessionMemory(
        last_order_id=memory.last_order_id,
        last_customer_id=memory.last_customer_id,
        last_returnable_order_id=memory.last_returnable_order_id,
        last_purchase_order_id=memory.last_purchase_order_id,
        last_product_candidates=matched_skus,
        last_sku=matched_skus[0] if len(matched_skus) == 1 else memory.last_sku,
    )
    return VariantFollowUpResolution(
        normalized_color=normalized_color,
        normalized_size=normalized_size,
        matched_skus=matched_skus,
        prompt_hint=_build_variant_follow_up_hint(
            matched_rows,
            normalized_color,
            normalized_size,
        ),
        updated_memory=updated_memory,
    )


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


def _parse_variant_reply(
    user_text: str,
    candidate_rows: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    tokens = re.findall(r"[A-Za-z]+", user_text)
    if not tokens or len(tokens) > 4:
        return None, None

    available_colors = {
        str(color)
        for color in (row.get("color") for row in candidate_rows)
        if _optional_str(color)
    }
    available_sizes = {
        str(size)
        for size in (row.get("size") for row in candidate_rows)
        if _optional_str(size)
    }
    normalized_color: str | None = None
    normalized_size: str | None = None
    recognized = 0

    for token in tokens:
        color = normalize_color(token)
        if color is not None and color in available_colors:
            normalized_color = color
            recognized += 1
            continue

        size = normalize_size(token)
        if size is not None and size in available_sizes:
            normalized_size = size
            recognized += 1
            continue

        if token.lower() not in FOLLOW_UP_FILLER_WORDS:
            return None, None

    if recognized == 0:
        return None, None
    return normalized_color, normalized_size


def _load_candidate_rows(
    candidate_skus: tuple[str, ...],
    catalog_repo: CatalogRepository,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sku in candidate_skus:
        row = catalog_repo.get_sku(sku)
        if row is None:
            continue
        resolved_sku = str(row["sku"])
        if resolved_sku in seen:
            continue
        seen.add(resolved_sku)
        rows.append(row)
    return rows


def _filter_candidate_rows(
    candidate_rows: list[dict[str, Any]],
    normalized_color: str | None,
    normalized_size: str | None,
) -> list[dict[str, Any]]:
    matched_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        row_color = _optional_str(row.get("color"))
        row_size = _optional_str(row.get("size"))
        if normalized_color is not None and row_color != normalized_color:
            continue
        if normalized_size is not None and row_size != normalized_size:
            continue
        matched_rows.append(row)
    return matched_rows


def _build_variant_follow_up_hint(
    matched_rows: list[dict[str, Any]],
    normalized_color: str | None,
    normalized_size: str | None,
) -> str:
    selected_parts: list[str] = []
    if normalized_color is not None:
        selected_parts.append(f"color {normalized_color}")
    if normalized_size is not None:
        selected_parts.append(f"size {normalized_size}")
    selected_detail = " and ".join(selected_parts) or "a variant detail"
    option_text = ", ".join(_format_candidate_option(row) for row in matched_rows)
    if len(matched_rows) == 1:
        row = matched_rows[0]
        return (
            "The user sent a variant-only follow-up reply. "
            f"Bind it only against the recent candidate SKUs. They selected {selected_detail}. "
            f"This uniquely resolves to SKU {row['sku']} ({_format_candidate_option(row)}). "
            "Do not invent any other SKU or product."
        )
    return (
        "The user sent a variant-only follow-up reply. "
        f"Bind it only against the recent candidate SKUs. They selected {selected_detail}. "
        f"The remaining valid candidates are: {option_text}. "
        "Do not invent a new SKU. Ask only for the remaining missing variant detail if needed."
    )


def _format_candidate_option(row: dict[str, Any]) -> str:
    parts = [str(row["product_name"])]
    if row.get("color"):
        parts.append(str(row["color"]))
    if row.get("size"):
        parts.append(str(row["size"]))
    return f"{' '.join(parts)} [{row['sku']}]"
