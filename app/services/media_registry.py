"""Media owner-type registry — audit P1-3.

Every ``owner_type`` that can bind a media asset registers how to check that
the target domain object exists and belongs to the current user. ``finalize``
in app/api/media.py calls ``authorize_bind`` instead of trusting the caller's
owner_ref_id — a cross-user or non-existent target is rejected (404).

Add new owner types here (and to ALLOWED_OWNER_TYPES in app/api/media.py).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.diet import Diet
from app.models.life import BodyMeasurement, InventoryItem
from app.models.locktimer import LockSession, LockSlotOccurrence, LockTaskOccurrence
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry


async def _model_exists(
    db: AsyncSession,
    model,
    id_col,
    ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """True if a row with ``id == ref_id`` exists and its owner column == user_id."""
    result = await db.execute(select(model.id).where(model.id == ref_id, id_col == user_id).limit(1))
    return result.first() is not None


async def _authorize_activity_log(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, ActivityLog, ActivityLog.user_id, ref_id, user_id)


async def _authorize_training_day(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, TrainingDay, TrainingDay.user_id, ref_id, user_id)


async def _authorize_training_log_entry(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, TrainingLogEntry, TrainingLogEntry.user_id, ref_id, user_id)


async def _authorize_inventory_item(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, InventoryItem, InventoryItem.user_id, ref_id, user_id)


async def _authorize_diet(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, Diet, Diet.user_id, ref_id, user_id)


async def _authorize_measurement(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, BodyMeasurement, BodyMeasurement.user_id, ref_id, user_id)


async def _authorize_lock_session(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, LockSession, LockSession.owner_id, ref_id, user_id)


async def _authorize_lock_slot_occurrence(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, LockSlotOccurrence, LockSlotOccurrence.owner_id, ref_id, user_id)


async def _authorize_lock_task_occurrence(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _model_exists(db, LockTaskOccurrence, LockTaskOccurrence.owner_id, ref_id, user_id)


async def _authorize_social_publication(db: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    from app.platform.social.models import SocialPublication

    return await _model_exists(db, SocialPublication, SocialPublication.owner_id, ref_id, user_id)


# owner_type → async authorize_bind(db, ref_id, user_id) -> bool
BIND_AUTHORIZERS: dict[str, object] = {
    "activity_log": _authorize_activity_log,
    "training_day": _authorize_training_day,
    "training_log_entry": _authorize_training_log_entry,
    "inventory_item": _authorize_inventory_item,
    "diet": _authorize_diet,
    "measurement": _authorize_measurement,
    "lock_session": _authorize_lock_session,
    "lock_slot_occurrence": _authorize_lock_slot_occurrence,
    "lock_task_occurrence": _authorize_lock_task_occurrence,
    "social_publication": _authorize_social_publication,
}


async def authorize_bind(db: AsyncSession, owner_type: str, ref_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """True if ``ref_id`` is a real domain object of ``owner_type`` owned by ``user_id``.

    Unknown owner types return False (caller rejects with 400/404).
    """
    fn = BIND_AUTHORIZERS.get(owner_type)
    if fn is None:
        return False
    return await fn(db, ref_id, user_id)  # type: ignore[misc]
