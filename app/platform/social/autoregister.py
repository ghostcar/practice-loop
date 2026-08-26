"""Platform Social — auto-registration of subjects from domain events (S1 bridge).

Domain modules (Tracker, Timer) call :func:`ensure_subject_registered` when they
create publishable objects (completed ActivityLog, LockSession). This makes
subjects available in the publish UI without manual SQL.

Guarantees:

- **Direction**: domain → social. This module never imports domain internals at
  module level; projection building goes through the registered adapter
  (which lazily touches domain models inside its methods).
- **Gated**: no-op when the ``social_enabled`` feature flag is off.
- **Idempotent**: unique ``(subject_type, domain_object_id)`` — re-running on
  the same object is a no-op (e.g. idempotent re-completion in ``complete_once``).
- **Best-effort**: a failure here NEVER breaks the domain operation. Errors are
  logged and swallowed.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social import get_adapter_registry
from app.platform.social.models import SocialSubject
from app.platform.social.repositories import register_subject

logger = logging.getLogger(__name__)


def _social_enabled() -> bool:
    """Read the social feature flag lazily (avoids import at module load)."""
    try:
        from app.config import settings

        return bool(getattr(settings, "social_enabled", False))
    except Exception:  # pragma: no cover - config import must never gate domain ops
        return False


async def ensure_subject_registered(
    db: AsyncSession,
    owner_id: uuid.UUID,
    subject_type: str,
    domain_object_id: str,
) -> SocialSubject | None:
    """Register a SocialSubject for a fresh domain object, if applicable.

    Returns the existing or newly-created subject, or ``None`` when social is
    disabled, the adapter is missing, or anything failed (best-effort).
    """
    if not _social_enabled():
        return None

    try:
        # Idempotent: unique (subject_type, domain_object_id).
        existing = await db.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == subject_type,
                SocialSubject.domain_object_id == str(domain_object_id),
                SocialSubject.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None

        namespace = subject_type.split(".", 1)[0]
        adapter = get_adapter_registry().get(namespace)
        if adapter is None:
            logger.debug("No social adapter for namespace %r — skip subject registration", namespace)
            return None

        # Build the immutable redacted projection via the adapter (best-effort).
        projection: dict | None = None
        try:
            projection = await adapter.build_redacted_projection(db, str(domain_object_id))
        except Exception:  # noqa: BLE001 - projection build must not block registration
            logger.warning("Social projection build failed for %s %s", subject_type, domain_object_id, exc_info=True)

        subject = await register_subject(
            db,
            owner_id,
            subject_type,
            str(domain_object_id),
            projection_snapshot=projection,
            projection_version=1,
        )
        return subject
    except Exception:  # noqa: BLE001 - social must never break a domain transaction
        logger.warning(
            "Social subject auto-registration failed for %s %s", subject_type, domain_object_id, exc_info=True
        )
        return None
