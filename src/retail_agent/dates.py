"""Date helpers used across the application."""

from __future__ import annotations

from datetime import date


ASSIGNMENT_TODAY = date(2026, 6, 19)


def parse_date(value: str) -> date:
    """Parse an ISO-8601 date string."""
    return date.fromisoformat(value)


def today_assignment_default() -> date:
    """Return the assignment's frozen notion of today."""
    return ASSIGNMENT_TODAY


def date_in_range(target: date, start: date, end: date) -> bool:
    """Return True when the target date falls in the inclusive range."""
    return start <= target <= end
