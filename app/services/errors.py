"""Shared exceptions for service layers."""


class NotFoundError(Exception):
    """Raised when a requested entity does not exist or is not owned by the user."""

    pass
