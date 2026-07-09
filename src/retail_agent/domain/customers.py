"""Customer resolution helpers."""

from __future__ import annotations

import re

from retail_agent.dates import parse_date
from retail_agent.db.repositories import CustomerRepository
from retail_agent.exceptions import AmbiguityError, NotFoundError, ValidationError
from retail_agent.types import Customer


def resolve_customer(name_or_id: str | None, repo: CustomerRepository) -> Customer | None:
    """Resolve a customer name or ID into a concrete customer record."""
    if name_or_id is None:
        return None

    for reference in candidate_customer_references(name_or_id):
        exact = repo.get_customer(reference)
        if exact is not None:
            return _row_to_customer(exact)

    candidates = find_customer_candidates(name_or_id, repo)
    if not candidates:
        if looks_like_customer_id(name_or_id):
            raise ValidationError(
                f"Customer reference '{name_or_id}' was not found. Use find_customer first or provide the customer name."
            )
        raise NotFoundError(f"No customer found for '{name_or_id}'.")
    if len(candidates) > 1:
        names = ", ".join(f"{customer.name} [{customer.customer_id}]" for customer in candidates)
        raise AmbiguityError(
            f"Multiple customers match '{name_or_id}'. Which customer did you mean? Options: {names}"
        )
    return candidates[0]


def find_customer_candidates(query: str, repo: CustomerRepository) -> list[Customer]:
    """Find customers by fuzzy name or email match."""
    rows = repo.find_by_name_or_email(query)
    return [_row_to_customer(row) for row in rows]


def candidate_customer_references(value: str) -> tuple[str, ...]:
    stripped = " ".join(value.strip().split())
    if not stripped:
        return ()

    candidates: list[str] = [stripped]
    normalized_id = _normalize_customer_id(stripped)
    if normalized_id is not None and normalized_id not in candidates:
        candidates.append(normalized_id)
    return tuple(candidates)


def looks_like_customer_id(value: str) -> bool:
    return _normalize_customer_id(value) is not None


def _normalize_customer_id(value: str) -> str | None:
    stripped = value.strip().upper()
    match = re.fullmatch(r"(?:C|CUS|CUST|CUSTOMER)[-\s]?(\d{1,6})", stripped)
    if match:
        return f"C-{int(match.group(1)):03d}"
    return None


def _row_to_customer(row: dict) -> Customer:
    return Customer(
        customer_id=row["customer_id"],
        name=row["name"],
        email=row["email"],
        joined_date=row["joined_date"]
        if hasattr(row["joined_date"], "isoformat")
        else parse_date(row["joined_date"]),
    )
