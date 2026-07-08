"""Customer resolution helpers."""

from __future__ import annotations

from retail_agent.dates import parse_date
from retail_agent.db.repositories import CustomerRepository
from retail_agent.exceptions import AmbiguityError, NotFoundError
from retail_agent.types import Customer


def resolve_customer(name_or_id: str | None, repo: CustomerRepository) -> Customer | None:
    """Resolve a customer name or ID into a concrete customer record."""
    if name_or_id is None:
        return None

    exact = repo.get_customer(name_or_id)
    if exact is not None:
        return _row_to_customer(exact)

    candidates = find_customer_candidates(name_or_id, repo)
    if not candidates:
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


def _row_to_customer(row: dict) -> Customer:
    return Customer(
        customer_id=row["customer_id"],
        name=row["name"],
        email=row["email"],
        joined_date=row["joined_date"]
        if hasattr(row["joined_date"], "isoformat")
        else parse_date(row["joined_date"]),
    )
