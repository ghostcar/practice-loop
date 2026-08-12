"""Platform Social — capability-based social sub-system (11_SOCIAL_SPEC.md, S0–S8).

This package MUST NOT import from app.locktimer, app.models.entity, app.api.tasks,
or any other Tracker/Timer domain internals. Domain modules depend on social;
social never depends on a domain module.

Belongs to app/platform/, NOT app/locktimer/ (03A_PRODUCT_VARIANTS.md §10).
"""

from __future__ import annotations

__all__ = [
    "SocialSubjectAdapter",
    "get_adapter_registry",
    "register_adapter",
    "SubjectType",
    "AdapterCapability",
]

from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Typed contracts shared across adapters
# ---------------------------------------------------------------------------

SubjectType = str  # "tracker.*" | "timer.*" namespaced


@runtime_checkable
class SocialSubjectAdapter(Protocol):
    """Versioned adapter contract for domain subjects (11_SOCIAL_SPEC.md §5A).

    Each enabled domain module (Tracker, Timer) registers ONE adapter instance
    covering all its subject types. The adapter resolves opaque social_subject
    ids back to domain objects, builds redacted projections, and executes
    authorized actions through domain application services.

    Adapter MUST NOT expose private ORM models, raw repositories, or generic
    callables to Social.
    """

    # Unique namespace for this adapter (e.g., "tracker", "timer").
    namespace: str

    # Schema version — bumped on breaking changes.
    version: int

    def subject_types(self) -> list[SubjectType]:
        """Return namespaced subject types this adapter handles."""
        ...

    async def authorize_subject(self, db: Any, actor_id: str, subject_id: str) -> bool:
        """Prove actor has ownership/access to the domain subject."""
        ...

    async def build_redacted_projection(
        self,
        db: Any,
        subject_id: str,
        requested_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Build an immutable redacted projection safe for Social storage."""
        ...

    def list_shareable_capabilities(self, subject_id: str) -> list[dict[str, Any]]:
        """Return allowlisted capabilities for this subject type."""
        ...

    async def validate_grant_constraints(
        self,
        db: Any,
        subject_id: str,
        grant_caps: dict[str, Any],
    ) -> list[str]:
        """Return validation errors (empty = valid)."""
        ...

    async def execute_authorized_action(
        self,
        db: Any,
        action_id: str,
        actor_id: str,
        grant_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a domain action through the application service exactly once."""
        ...

    async def on_revoke_or_block(self, db: Any, subject_id: str, actor_id: str) -> None:
        """Lifecycle hook: revoke/block cleanup."""
        ...

    async def export_data(self, db: Any, subject_id: str) -> dict[str, Any]:
        """Export all shareable data for this subject (privacy export)."""
        ...

    async def delete_or_pseudonymize(self, db: Any, subject_id: str) -> None:
        """Account deletion hook."""
        ...


@runtime_checkable
class AdapterCapability(Protocol):
    """Describes one shareable capability for a subject type."""

    name: str
    description: str
    scope: str  # "read" | "write" | "verify"
    requires_grant_accept: bool


# ---------------------------------------------------------------------------
# Adapter registry (module-level singleton)
# ---------------------------------------------------------------------------

_registry: dict[str, SocialSubjectAdapter] = {}


def register_adapter(adapter: SocialSubjectAdapter) -> None:
    """Register a domain adapter. Called once at startup per enabled module."""
    if adapter.namespace in _registry:
        raise ValueError(f"SocialSubjectAdapter namespace '{adapter.namespace}' already registered")
    _registry[adapter.namespace] = adapter


def get_adapter_registry() -> dict[str, SocialSubjectAdapter]:
    """Return the current adapter registry (read-only for callers)."""
    return dict(_registry)
