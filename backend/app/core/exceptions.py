"""Domain-level exceptions decoupled from HTTP and SQLAlchemy persistence details."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for business/domain errors."""


class ResourceNotFoundError(DomainError):
    """Raised when a requested domain entity cannot be found."""


class ConflictError(DomainError):
    """Raised when an operation violates a uniqueness or state constraint."""


class DomainValidationError(DomainError):
    """Raised when domain preconditions or input semantics are invalid."""
