"""Money helpers used across pricing and reporting."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Convert a numeric-like value to Decimal without float math."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def quantize_cents(amount: Decimal) -> Decimal:
    """Round an amount to cents using half-up rounding."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def apply_percent_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Apply a percentage discount to an amount and round to cents."""
    discounted = amount * (Decimal("1") - (pct / HUNDRED))
    return quantize_cents(discounted)
