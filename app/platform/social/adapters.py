"""Platform Social — domain adapters (S6).

Tracker adapter and Timer adapter with read/verify projections.
Write-action execution remains intentionally unimplemented.
Registered at startup in main.py when composition flags are enabled.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tracker adapter
# ---------------------------------------------------------------------------


class TrackerSocialAdapter:
    """SocialSubjectAdapter for Tracker domain objects (ActivityLog, Entity).

    Covers subject types:
    - tracker.activity_log — public redacted projection of a completed activity
    - tracker.entity — reference to a catalog entity

    Built projections are immutable snapshots — no live view of changing domain state.
    """

    namespace: str = "tracker"
    version: int = 1

    def subject_types(self) -> list[str]:
        return ["tracker.activity_log", "tracker.entity"]

    async def authorize_subject(self, db: Any, actor_id: str, subject_id: str) -> bool:
        """Check ownership — subject_id is the string form of the domain object pk."""
        from uuid import UUID

        from sqlalchemy import select

        from app.models.activity_log import ActivityLog
        from app.models.entity import Entity

        try:
            sid = UUID(subject_id)
        except (ValueError, AttributeError):
            return False

        # Try ActivityLog
        result = await db.execute(
            select(ActivityLog).where(ActivityLog.id == sid, ActivityLog.user_id == UUID(actor_id))
        )
        if result.scalar_one_or_none() is not None:
            return True

        # Try Entity
        result = await db.execute(
            select(Entity).where(
                Entity.id == sid,
                (Entity.owner_id == UUID(actor_id)) | (Entity.owner_id.is_(None)),
            )
        )
        return result.scalar_one_or_none() is not None

    async def build_redacted_projection(
        self,
        db: Any,
        subject_id: str,
        requested_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Build an immutable redacted snapshot safe for Social storage.

        Strips: raw_llm_response, penalty_details, personal notes, user_id.
        """
        from uuid import UUID

        from sqlalchemy import select

        from app.models.activity_log import ActivityLog
        from app.models.entity import Entity

        sid = UUID(subject_id)

        # Build from ActivityLog
        result = await db.execute(select(ActivityLog).where(ActivityLog.id == sid))
        log = result.scalar_one_or_none()
        if log is not None:
            return {
                "type": "tracker.activity_log",
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "cleaned_response": log.cleaned_response,
                # Never expose raw_llm_response, penalty_details, user_prompt
            }

        # Build from Entity
        result = await db.execute(select(Entity).where(Entity.id == sid))
        entity = result.scalar_one_or_none()
        if entity is not None:
            return {
                "type": "tracker.entity",
                "real_name": entity.real_name,
                "entity_type": entity.type,
                "params_schema": entity.params_schema,
                "risk_level": getattr(entity, "risk_level", None),
            }

        return {}

    def list_shareable_capabilities(self, subject_id: str) -> list[dict[str, Any]]:
        return [
            {
                "name": "tracker.activity.view_summary",
                "description": "View activity summary (status, cleaned response)",
                "scope": "read",
                "requires_grant_accept": True,
            },
            {
                "name": "tracker.activity.view_details",
                "description": "View full activity details",
                "scope": "read",
                "requires_grant_accept": True,
            },
            {
                "name": "tracker.activity.verify",
                "description": "Submit verification vote on this activity",
                "scope": "verify",
                "requires_grant_accept": True,
            },
        ]

    async def validate_grant_constraints(
        self,
        db: Any,
        subject_id: str,
        grant_caps: dict[str, Any],
    ) -> list[str]:
        """Validate grant caps against allowlisted capabilities."""
        allowlisted = {c["name"] for c in self.list_shareable_capabilities(subject_id)}
        errors: list[str] = []
        for cap in grant_caps.get("caps", []):
            if cap not in allowlisted:
                errors.append(f"Capability '{cap}' not allowlisted for this subject")
        return errors

    async def execute_authorized_action(
        self,
        db: Any,
        action_id: str,
        actor_id: str,
        grant_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a domain action; write-action execution is not enabled yet."""
        return {"status": "not_implemented", "action_id": action_id}

    async def on_revoke_or_block(self, db: Any, subject_id: str, actor_id: str) -> None:
        """Cleanup on revoke/block; these adapters have no write-side effects."""
        pass

    async def export_data(self, db: Any, subject_id: str) -> dict[str, Any]:
        """Export all shareable data for this subject."""
        projection = await self.build_redacted_projection(db, subject_id)
        return projection

    async def delete_or_pseudonymize(self, db: Any, subject_id: str) -> None:
        """Account deletion — no additional cleanup needed for tracker subjects."""
        pass


# ---------------------------------------------------------------------------
# Timer adapter (read/verify implementation; write actions remain out of scope)
# ---------------------------------------------------------------------------


class TimerSocialAdapter:
    """SocialSubjectAdapter for LockTimer domain objects (LockSession).

    Covers subject types:
    - timer.session — redacted projection of a lock session

    Redaction rules: NEVER expose ``random_seed_encrypted``, ``random_seed_commitment``
    or any device-bound key material. Only state/planning metadata is shareable.
    """

    namespace: str = "timer"
    version: int = 1

    def subject_types(self) -> list[str]:
        return ["timer.session", "timer.slot_occurrence", "timer.task_occurrence"]

    async def authorize_subject(self, db: Any, actor_id: str, subject_id: str) -> bool:
        """Check ownership of a lock session by id."""
        from uuid import UUID

        from sqlalchemy import select

        from app.models.locktimer import LockSession

        try:
            sid = UUID(subject_id)
        except (ValueError, AttributeError):
            return False
        result = await db.execute(
            select(LockSession).where(LockSession.id == sid, LockSession.owner_id == UUID(actor_id))
        )
        return result.scalar_one_or_none() is not None

    async def build_redacted_projection(
        self,
        db: Any,
        subject_id: str,
        requested_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Build an immutable redacted snapshot of a lock session.

        Shareable: state, duration type, timezone, privacy mode, timestamps.
        Never shareable: random seeds/commitments, device token material.
        """
        from uuid import UUID

        from sqlalchemy import select

        from app.models.locktimer import LockSession

        try:
            sid = UUID(subject_id)
        except (ValueError, AttributeError):
            return {}

        result = await db.execute(select(LockSession).where(LockSession.id == sid))
        session = result.scalar_one_or_none()
        if session is None:
            return {}

        return {
            "type": "timer.session",
            "state": session.state,
            "duration_type": session.duration_type,
            "timezone": session.timezone,
            "privacy_mode": getattr(session, "privacy_mode", "private"),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "requested_start_at": (
                session.requested_start_at.isoformat() if getattr(session, "requested_start_at", None) else None
            ),
            "original_end_at": (
                session.original_end_at.isoformat() if getattr(session, "original_end_at", None) else None
            ),
        }

    def list_shareable_capabilities(self, subject_id: str) -> list[dict[str, Any]]:
        return [
            {
                "name": "timer.session.view_summary",
                "description": "View lock session summary (state, timing)",
                "scope": "read",
                "requires_grant_accept": True,
            },
            {
                "name": "timer.session.verify",
                "description": "Submit verification vote on this session",
                "scope": "verify",
                "requires_grant_accept": True,
            },
        ]

    async def validate_grant_constraints(
        self,
        db: Any,
        subject_id: str,
        grant_caps: dict[str, Any],
    ) -> list[str]:
        """Validate grant caps against allowlisted capabilities."""
        allowlisted = {c["name"] for c in self.list_shareable_capabilities(subject_id)}
        errors: list[str] = []
        for cap in grant_caps.get("caps", []):
            if cap not in allowlisted:
                errors.append(f"Capability '{cap}' not allowlisted for this subject")
        return errors

    async def execute_authorized_action(
        self,
        db: Any,
        action_id: str,
        actor_id: str,
        grant_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a domain action; write-action execution is not enabled yet."""
        return {"status": "not_implemented", "action_id": action_id}

    async def on_revoke_or_block(self, db: Any, subject_id: str, actor_id: str) -> None:
        pass

    async def export_data(self, db: Any, subject_id: str) -> dict[str, Any]:
        return await self.build_redacted_projection(db, subject_id)

    async def delete_or_pseudonymize(self, db: Any, subject_id: str) -> None:
        pass
