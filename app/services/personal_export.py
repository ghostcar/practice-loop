"""Portable, versioned export of all owner-scoped Personal data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import UserAchievement
from app.models.activity_log import ActivityLog
from app.models.aftercare import AftercareEntry
from app.models.api_token import ApiToken
from app.models.calendar import AvailabilityWindow, CalendarOverride, CalendarTemplate
from app.models.care import CareCourse, CareEntry, CareProduct, CareRoutine
from app.models.catalog import ActivityCatalogItem
from app.models.consent import ConsentRecord
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview
from app.models.entity import Entity
from app.models.health import CycleEvent, CycleSettings, HealthState, LabRecord
from app.models.insights import InsightRun
from app.models.journal import JournalEntry, JournalPartner
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.llm_config import LLMProviderConfig
from app.models.locktimer import LockSession
from app.models.media import MediaAsset, MediaVerificationResult, VerificationChallenge
from app.models.medication import Medication, MedIntake, MedKit, MedSchedule, MedStock
from app.models.notification import Notification
from app.models.opt_in import UserEntityOptIn
from app.models.points import PenaltyRedemption, PointsProfile, PointsTransaction
from app.models.progress import UserProgress
from app.models.prompt_template import PromptTemplate
from app.models.push_device import PushDevice
from app.models.reminder_log import ReminderLog
from app.models.session import ActivitySession
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry
from app.models.user import User

EXPORT_SCHEMA_VERSION = 2

_DIRECT_USER_MODELS = (
    ActivityLog,
    ApiToken,
    AftercareEntry,
    AvailabilityWindow,
    BodyMeasurement,
    CalendarOverride,
    CalendarTemplate,
    CareCourse,
    CareEntry,
    CareProduct,
    CareRoutine,
    ConsentRecord,
    CycleEvent,
    CycleSettings,
    Diet,
    DietConsumption,
    DietEvaluation,
    DietItem,
    DietTrainingReview,
    HealthState,
    InsightRun,
    InventoryItem,
    JournalEntry,
    JournalPartner,
    LabRecord,
    LLMProviderConfig,
    MediaAsset,
    Medication,
    MedIntake,
    MedKit,
    MedSchedule,
    MedStock,
    Notification,
    PenaltyRedemption,
    PointsProfile,
    PointsTransaction,
    PromptTemplate,
    PushDevice,
    ReminderLog,
    ScheduleRule,
    TrainingDay,
    TrainingLogEntry,
    UserEntityOptIn,
    UserAchievement,
    VerificationChallenge,
)

_EXCLUDED_COLUMNS = {
    "password_hash",
    "api_key_encrypted",
    "token_hash",
    "device_token",
    "code_hmac",
    "expected_code_hmac",
    "telegram_link_code",
    "telegram_link_code_expires",
    "file_path",
    "thumbnail_path",
}


def _serialize_row(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in _EXCLUDED_COLUMNS:
            continue
        value = getattr(row, column.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[column.name] = value
    return result


async def _select_rows(db: AsyncSession, model, predicate) -> list[dict[str, Any]]:
    rows = (await db.execute(select(model).where(predicate))).scalars().all()
    return [_serialize_row(row) for row in rows]


async def build_personal_export(db: AsyncSession, user: User) -> dict[str, Any]:
    """Return the complete portable manifest for one user's Personal contour."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for model in _DIRECT_USER_MODELS:
        user_column = getattr(model, "user_id", None)
        if user_column is None:
            continue
        sections[model.__tablename__] = await _select_rows(db, model, user_column == user.id)

    for model in (
        Entity,
        ActivitySession,
        ActivityCatalogItem,
        LockSession,
        MediaAsset,
        MediaVerificationResult,
        VerificationChallenge,
    ):
        owner_column = model.owner_id
        sections[model.__tablename__] = await _select_rows(db, model, owner_column == user.id)

    progress = await db.get(UserProgress, user.id)
    sections[UserProgress.__tablename__] = [_serialize_row(progress)] if progress else []

    # Child/audit tables are resolved through their owned roots. This keeps the
    # export owner-scoped even when a child table intentionally has no user_id.
    from app.models.insights import InsightFinding
    from app.models.locktimer import (
        LockAuditEvent,
        LockInnerPeriod,
        LockLlmProposal,
        LockOutboxEvent,
        LockPenaltyEvent,
        LockSessionSnapshot,
        LockSlotOccurrence,
        LockSlotRule,
        LockTagViolation,
        LockTaskOccurrence,
        LockTaskRule,
    )
    from app.models.session_history import ActivitySessionHistory
    from app.models.task_history import ActivityTaskHistory

    activity_ids = select(ActivityLog.id).where(ActivityLog.user_id == user.id)
    session_ids = select(ActivitySession.id).where(ActivitySession.owner_id == user.id)
    insight_ids = select(InsightRun.id).where(InsightRun.user_id == user.id)
    lock_ids = select(LockSession.id).where(LockSession.owner_id == user.id)
    calendar_ids = select(CalendarTemplate.id).where(CalendarTemplate.user_id == user.id)
    diet_ids = select(Diet.id).where(Diet.user_id == user.id)
    sections[ActivityTaskHistory.__tablename__] = await _select_rows(
        db, ActivityTaskHistory, ActivityTaskHistory.task_id.in_(activity_ids)
    )
    sections[ActivitySessionHistory.__tablename__] = await _select_rows(
        db, ActivitySessionHistory, ActivitySessionHistory.session_id.in_(session_ids)
    )
    sections[InsightFinding.__tablename__] = await _select_rows(
        db, InsightFinding, InsightFinding.run_id.in_(insight_ids)
    )
    sections[AvailabilityWindow.__tablename__] = await _select_rows(
        db, AvailabilityWindow, AvailabilityWindow.template_id.in_(calendar_ids)
    )
    sections[DietItem.__tablename__] = await _select_rows(db, DietItem, DietItem.diet_id.in_(diet_ids))
    for model in (
        LockSessionSnapshot,
        LockInnerPeriod,
        LockSlotRule,
        LockSlotOccurrence,
        LockTaskRule,
        LockTaskOccurrence,
        LockPenaltyEvent,
        LockAuditEvent,
        LockLlmProposal,
        LockTagViolation,
    ):
        sections[model.__tablename__] = await _select_rows(db, model, model.session_id.in_(lock_ids))
    sections[LockOutboxEvent.__tablename__] = await _select_rows(
        db,
        LockOutboxEvent,
        (LockOutboxEvent.aggregate_type == "lock_session") & LockOutboxEvent.aggregate_id.in_(lock_ids),
    )

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "locale": user.locale,
            "theme": user.theme,
            "timezone": user.timezone,
            "prefs": user.prefs,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "sections": sections,
        "counts": {name: len(rows) for name, rows in sections.items()},
    }
