"""Consent policy registry and append-only consent operations (ADR-104).

Consent is durable for a purpose + terms version. It is requested once and
remains effective until the user explicitly revokes it or the terms version is
bumped. Enabling a new profile module introduces that module's consent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentRecord
from app.models.user import User


@dataclass(frozen=True)
class ConsentPurpose:
    key: str
    terms_version: str = "1"
    module: bool = False


PROFILE_MODULES: tuple[str, ...] = (
    "tracker",
    "timer",
    "medication",
    "health",
    "journal",
    "care",
    "catalog",
    "insights",
    "aftercare",
    "social",
)

PURPOSES: dict[str, ConsentPurpose] = {
    **{f"module:{name}": ConsentPurpose(f"module:{name}", module=True) for name in PROFILE_MODULES},
    "byok_provider": ConsentPurpose("byok_provider"),
    "llm_expanded": ConsentPurpose("llm_expanded"),
    "media_verification": ConsentPurpose("media_verification"),
    "data_processing": ConsentPurpose("data_processing"),
}


def purpose(key: str) -> ConsentPurpose:
    item = PURPOSES.get(key)
    if item is None:
        raise HTTPException(400, f"Unknown consent purpose: {key}")
    return item


async def latest_record(db: AsyncSession, user_id: uuid.UUID, key: str) -> ConsentRecord | None:
    return (
        (
            await db.execute(
                select(ConsentRecord)
                .where(ConsentRecord.user_id == user_id, ConsentRecord.consent_type == key)
                .order_by(ConsentRecord.version.desc())
            )
        )
        .scalars()
        .first()
    )


async def has_consent(db: AsyncSession, user_id: uuid.UUID, key: str) -> bool:
    expected = purpose(key)
    row = await latest_record(db, user_id, key)
    return bool(row and row.state == "granted" and row.terms_version == expected.terms_version)


async def require_consent(db: AsyncSession, user_id: uuid.UUID, key: str) -> None:
    if not await has_consent(db, user_id, key):
        raise HTTPException(
            status_code=428,
            detail={"code": "consent_required", "consent_type": key, "url": f"/consent/setup?required={key}"},
        )


async def record_consent(
    db: AsyncSession,
    user: User,
    key: str,
    state: str,
    *,
    scope: str | None = None,
    notes: str | None = None,
) -> ConsentRecord:
    """Append an idempotent grant/revoke event while serializing per user."""
    if state not in {"granted", "revoked"}:
        raise HTTPException(400, "Invalid consent state")
    expected = purpose(key)

    # Serialize version allocation on PostgreSQL. SQLite test transactions are
    # already single-writer; the unique constraint remains the final guard.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    latest = await latest_record(db, user.id, key)
    if latest and latest.state == state and latest.terms_version == expected.terms_version:
        return latest

    row = ConsentRecord(
        user_id=user.id,
        consent_type=key,
        state=state,
        scope=(scope or "").strip() or None,
        notes=(notes or "").strip() or None,
        version=(latest.version + 1) if latest else 1,
        terms_version=expected.terms_version,
        revoked_at=datetime.now(UTC) if state == "revoked" else None,
    )
    db.add(row)
    await db.flush()
    return row


async def missing_consents(db: AsyncSession, user_id: uuid.UUID, keys: list[str]) -> list[str]:
    missing: list[str] = []
    for key in keys:
        if not await has_consent(db, user_id, key):
            missing.append(key)
    return missing
