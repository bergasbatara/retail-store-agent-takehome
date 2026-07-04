"""Shared domain exceptions."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-level application errors."""


class NotFoundError(DomainError):
    """Raised when a requested entity cannot be found."""


class AmbiguityError(DomainError):
    """Raised when user input matches multiple possible entities."""


class ValidationError(DomainError):
    """Raised when an input fails domain validation."""


class InsufficientInventoryError(DomainError):
    """Raised when inventory is not sufficient for a requested operation."""
