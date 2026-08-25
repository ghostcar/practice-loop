"""Sexual Journal — Business Logic Service Layer.

Extracted from app/api/journal.py (ADR-164) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - ensure_timer_slot_entry / get_pending_slot_entry  — timer↔journal bridge
  - journal_summary                                   — dashboard summary
  - get_journal_page_context                          — template context
  - create_entry / complete_entry / delete_entry
  - create_partner / delete_partner
  - attach_entry_media
  - json_* variants for mobile API
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import (
    JOURNAL_SOURCES,
    JOURNAL_STATUSES,
    PROTECTION_TYPES,
    REACTION_CHOICES,
    SCALE_1_5,
    JournalEntry,
    JournalPartner,
)
from app.models.media import MediaAsset
from app.services.errors import NotFoundError
from app.timeutils import local_today

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Bodies
# ─────────────────────────────────────────────────────────────────────────────


class EntryBody(BaseModel):
    entry_date: date
    partner_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    activity_log_id: uuid.UUID | None = None
    care_product_ids: list[uuid.UUID] | None = None


class CompleteBody(BaseModel):
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    care_product_ids: list[uuid.UUID] | None = None


class PartnerBody(BaseModel):
    name: str
    notes: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot
# ─────────────────────────────────────────────────────────────────────────────


async def cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    try:
        from app.models.health import CycleEvent, CycleSettings
        from app.services.health_service import cycle_phase as _cycle_phase
        from app.services.health_service import day_of_cycle as _day_of_cycle
    except Exception:
        return None, None
    settings_row = (
        await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))
    ).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    day = _day_of_cycle(list(events), settings_row, entry_date)
    if day is None:
        return None, None
    ph = _cycle_phase(
        day,
        settings_row.cycle_length if settings_row else 28,
        settings_row.period_length if settings_row else 5,
    )
    return ph, day


# ─────────────────────────────────────────────────────────────────────────────
# Timer slot → auto journal entry
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_timer_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
    entry_date: date,
) -> JournalEntry | None:
    existing = (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    cycle_ph, cycle_day = await cycle_snapshot(db, user_id, entry_date)
    entry = JournalEntry(
        user_id=user_id,
        entry_date=entry_date,
        status="draft",
        source="timer_slot",
        timer_session_id=session_id,
        slot_occurrence_id=slot_occurrence_id,
        cycle_phase=cycle_ph,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_pending_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
) -> JournalEntry | None:
    return (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
                JournalEntry.status == "draft",
            )
        )
    ).scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary
# ─────────────────────────────────────────────────────────────────────────────


async def journal_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from datetime import timedelta

    today = local_today()
    since = today - timedelta(days=30)
    rows = (
        (
            await db.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id, JournalEntry.entry_date >= since)
                .order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    total = (await db.execute(select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id))).scalar() or 0
    pending = (
        await db.execute(
            select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id, JournalEntry.status == "draft")
        )
    ).scalar() or 0
    satisfactions = [r.satisfaction for r in rows if r.satisfaction is not None]
    last = rows[0] if rows else None
    return {
        "count_30d": len(rows),
        "total": total,
        "pending": pending,
        "last_date": last.entry_date.isoformat() if last else None,
        "last_type": last.activity_type if last else None,
        "avg_satisfaction": round(sum(satisfactions) / len(satisfactions), 1) if satisfactions else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────


async def media_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict]]:
    rows = (
        (
            await db.execute(
                select(MediaAsset)
                .where(MediaAsset.owner_id == user_id, MediaAsset.owner_type == "journal_entry")
                .order_by(MediaAsset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[dict]] = {}
    for a in rows:
        key = str(a.owner_ref_id) if a.owner_ref_id else ""
        if not key:
            continue
        out.setdefault(key, []).append(
            {
                "id": str(a.id),
                "has_thumbnail": a.thumbnail_path is not None,
                "is_image": (a.mime_type or "").startswith("image/"),
                "caption": a.caption,
            }
        )
    return out


async def activity_title_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    from app.models.activity_log import ActivityLog

    ids = (
        (
            await db.execute(
                select(JournalEntry.activity_log_id).where(
                    JournalEntry.user_id == user_id, JournalEntry.activity_log_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(ActivityLog).where(ActivityLog.id.in_(ids)))).scalars().all()
    return {str(r.id): (r.title_override or r.selected_entity_name or str(r.id)[:8]) for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Validators / resolvers
# ─────────────────────────────────────────────────────────────────────────────


def parse_scale(raw: str, field_name: str) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(f"Invalid {field_name} (1-5)") from None
    if v not in SCALE_1_5:
        raise ValueError(f"Invalid {field_name} (1-5)")
    return v


def parse_int(raw: str, field_name: str, minimum: int = 0, maximum: int = 10000) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(f"Invalid {field_name}") from None
    if v < minimum or v > maximum:
        raise ValueError(f"Invalid {field_name} (out of range)")
    return v


def validate_partner_id(partner_id: str) -> uuid.UUID | None:
    if not partner_id.strip():
        return None
    try:
        return uuid.UUID(partner_id.strip())
    except ValueError:
        raise ValueError("Invalid partner_id") from None


async def validate_activity_log(
    db: AsyncSession, activity_log_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> uuid.UUID | None:
    from app.models.activity_log import ActivityLog

    if not activity_log_id:
        return None
    try:
        aid = uuid.UUID(str(activity_log_id))
    except ValueError:
        raise ValueError("Invalid activity_log_id") from None
    task = (
        await db.execute(select(ActivityLog).where(ActivityLog.id == aid, ActivityLog.user_id == user_id))
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Activity not found")
    return aid


async def validate_care_products(
    db: AsyncSession, care_product_ids: str | list[uuid.UUID] | None, user_id: uuid.UUID
) -> list[str] | None:
    if care_product_ids is None:
        return None
    if isinstance(care_product_ids, str):
        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        if not raw:
            return None
        try:
            parsed = [uuid.UUID(x) for x in raw]
        except ValueError:
            raise ValueError("Invalid care_product_ids") from None
    else:
        parsed = list(care_product_ids)
    if not parsed:
        return None
    from app.models.care import CareProduct

    rows = (
        (await db.execute(select(CareProduct.id).where(CareProduct.id.in_(parsed), CareProduct.user_id == user_id)))
        .scalars()
        .all()
    )
    if len(rows) != len(set(parsed)):
        raise ValueError("One or more care products not found")
    return [str(x) for x in parsed]


async def resolve_catalog_item(db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID):
    from app.models.catalog import ActivityCatalogItem

    if not catalog_item_id:
        return None
    try:
        cid = uuid.UUID(str(catalog_item_id))
    except ValueError:
        raise ValueError("Invalid catalog_item_id") from None
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == cid,
                ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Catalog item not found")
    return item


async def validate_partner(db: AsyncSession, partner_id: str, user_id: uuid.UUID) -> uuid.UUID | None:
    pid = validate_partner_id(partner_id)
    if pid is None:
        return None
    partner = (
        await db.execute(select(JournalPartner).where(JournalPartner.id == pid, JournalPartner.user_id == user_id))
    ).scalar_one_or_none()
    if partner is None:
        raise NotFoundError("Partner not found")
    return pid


# ─────────────────────────────────────────────────────────────────────────────
# Entry field application
# ─────────────────────────────────────────────────────────────────────────────


def apply_entry_fields(
    entry: JournalEntry,
    *,
    entry_date: date,
    partner_id: uuid.UUID | None,
    catalog_item_id: uuid.UUID | None,
    activity_type: str,
    duration_minutes: int | None,
    desire_before: int | None,
    arousal_before: int | None,
    protection: str,
    orgasms: int | None,
    intensity: int | None,
    satisfaction: int | None,
    pleasure: int | None,
    reactions: list[str] | None,
    emotional_state: list[str] | None,
    aftercare: str,
    recovery: int | None,
    notes: str,
    activity_log_id: uuid.UUID | None,
    care_product_ids: list[str] | None = None,
) -> None:
    entry.entry_date = entry_date
    entry.partner_id = partner_id
    entry.catalog_item_id = catalog_item_id
    entry.care_product_ids = care_product_ids
    entry.activity_type = (activity_type or "").strip()[:100] or None
    entry.duration_minutes = duration_minutes
    entry.desire_before = desire_before
    entry.arousal_before = arousal_before
    entry.protection = protection
    entry.orgasms = orgasms
    entry.intensity = intensity
    entry.satisfaction = satisfaction
    entry.pleasure = pleasure
    entry.reactions = reactions
    entry.emotional_state = emotional_state
    entry.aftercare = (aftercare or "").strip() or None
    entry.recovery = recovery
    entry.notes = (notes or "").strip() or None
    entry.activity_log_id = activity_log_id
    entry.status = "completed"


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────


def entry_view(e: JournalEntry, partner_names: dict[str, str]) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "partner_id": str(e.partner_id) if e.partner_id else None,
        "partner_name": partner_names.get(str(e.partner_id)) if e.partner_id else None,
        "catalog_item_id": str(e.catalog_item_id) if e.catalog_item_id else None,
        "activity_type": e.activity_type,
        "duration_minutes": e.duration_minutes,
        "desire_before": e.desire_before,
        "arousal_before": e.arousal_before,
        "protection": e.protection,
        "orgasms": e.orgasms,
        "intensity": e.intensity,
        "satisfaction": e.satisfaction,
        "pleasure": e.pleasure,
        "reactions": e.reactions or [],
        "emotional_state": e.emotional_state or [],
        "care_product_ids": [str(x) for x in (e.care_product_ids or [])],
        "aftercare": e.aftercare,
        "recovery": e.recovery,
        "notes": e.notes,
        "status": e.status,
        "source": e.source,
        "activity_log_id": str(e.activity_log_id) if e.activity_log_id else None,
        "slot_occurrence_id": str(e.slot_occurrence_id) if e.slot_occurrence_id else None,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


def entry_json(e: JournalEntry) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "partner_id": str(e.partner_id) if e.partner_id else None,
        "catalog_item_id": str(e.catalog_item_id) if e.catalog_item_id else None,
        "activity_type": e.activity_type,
        "duration_minutes": e.duration_minutes,
        "desire_before": e.desire_before,
        "arousal_before": e.arousal_before,
        "protection": e.protection,
        "orgasms": e.orgasms,
        "intensity": e.intensity,
        "satisfaction": e.satisfaction,
        "pleasure": e.pleasure,
        "reactions": e.reactions or [],
        "emotional_state": e.emotional_state or [],
        "aftercare": e.aftercare,
        "recovery": e.recovery,
        "notes": e.notes,
        "status": e.status,
        "source": e.source,
        "activity_log_id": str(e.activity_log_id) if e.activity_log_id else None,
        "slot_occurrence_id": str(e.slot_occurrence_id) if e.slot_occurrence_id else None,
        "care_product_ids": [str(x) for x in (e.care_product_ids or [])],
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_journal_page_context(db: AsyncSession, user) -> dict:
    from app.services.catalog_service import catalog_options

    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    partners = (
        (
            await db.execute(
                select(JournalPartner).where(JournalPartner.user_id == user.id).order_by(JournalPartner.name.asc())
            )
        )
        .scalars()
        .all()
    )
    partner_names = {str(p.id): p.name for p in partners}
    media = await media_map(db, user.id)
    activity_titles = await activity_title_map(db, user.id)

    from app.models.activity_log import ActivityLog

    recent_activities = (
        (
            await db.execute(
                select(ActivityLog)
                .where(ActivityLog.user_id == user.id)
                .order_by(ActivityLog.created_at.desc())
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    recent_activity_options = [
        {"id": str(a.id), "label": (a.title_override or a.selected_entity_name or str(a.id)[:8])[:60]}
        for a in recent_activities
    ]

    pending_entries = [e for e in entries if e.status == "draft"]
    done_entries = [e for e in entries if e.status != "draft"]

    catalog_items = await catalog_options(db, user.id, domain="journal")

    care_products: list[dict] = []
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name).limit(200)
        )
        care_products = [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        pass

    return {
        "pending_entries": [entry_view(e, partner_names) for e in pending_entries],
        "entries": [entry_view(e, partner_names) for e in done_entries],
        "partners": [
            {
                "id": str(p.id),
                "name": p.name,
                "notes": p.notes,
                "entries_count": sum(1 for e in entries if e.partner_id == p.id),
            }
            for p in partners
        ],
        "media": media,
        "activity_titles": activity_titles,
        "recent_activities": recent_activity_options,
        "catalog_items": catalog_items,
        "care_products": care_products,
        "scales": list(SCALE_1_5),
        "protection_types": list(PROTECTION_TYPES),
        "reaction_choices": list(REACTION_CHOICES),
        "journal_statuses": list(JOURNAL_STATUSES),
        "journal_sources": list(JOURNAL_SOURCES),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Entries
# ─────────────────────────────────────────────────────────────────────────────


async def create_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_date: str,
    partner_id: str,
    activity_type: str,
    duration_minutes: str,
    desire_before: str,
    arousal_before: str,
    protection: str,
    orgasms: str,
    intensity: str,
    satisfaction: str,
    pleasure: str,
    reactions: str,
    emotional_state: str,
    aftercare: str,
    recovery: str,
    notes: str,
    activity_log_id: str,
    catalog_item_id: str,
    care_product_ids: str,
) -> JournalEntry:
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise ValueError("Invalid entry_date (ISO 8601)") from None

    partner_uuid = validate_partner_id(partner_id)
    if partner_uuid is not None:
        p = (
            await db.execute(
                select(JournalPartner).where(JournalPartner.id == partner_uuid, JournalPartner.user_id == user_id)
            )
        ).scalar_one_or_none()
        if p is None:
            raise NotFoundError("Partner not found")

    if protection not in PROTECTION_TYPES:
        protection = "none"
    reaction_list = [x.strip() for x in reactions.split(",") if x.strip()] if reactions.strip() else None
    emotion_list = [x.strip() for x in emotional_state.split(",") if x.strip()] if emotional_state.strip() else None
    aid = await validate_activity_log(db, activity_log_id, user_id)
    catalog_item = await resolve_catalog_item(db, catalog_item_id, user_id)
    care_uuids = await validate_care_products(db, care_product_ids, user_id)

    cycle_ph, cycle_day = await cycle_snapshot(db, user_id, d)

    entry = JournalEntry(
        user_id=user_id,
        entry_date=d,
        status="completed",
        source="activity" if aid else "manual",
        cycle_phase=cycle_ph,
        cycle_day=cycle_day,
    )
    apply_entry_fields(
        entry,
        entry_date=d,
        partner_id=partner_uuid,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else activity_type,
        duration_minutes=parse_int(duration_minutes, "duration_minutes"),
        desire_before=parse_scale(desire_before, "desire_before"),
        arousal_before=parse_scale(arousal_before, "arousal_before"),
        protection=protection,
        orgasms=parse_int(orgasms, "orgasms", maximum=100),
        intensity=parse_scale(intensity, "intensity"),
        satisfaction=parse_scale(satisfaction, "satisfaction"),
        pleasure=parse_scale(pleasure, "pleasure"),
        reactions=reaction_list,
        emotional_state=emotion_list,
        aftercare=aftercare,
        recovery=parse_scale(recovery, "recovery"),
        notes=notes,
        activity_log_id=aid,
        care_product_ids=care_uuids,
    )
    db.add(entry)
    await db.flush()
    return entry


async def complete_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    activity_type: str,
    duration_minutes: str,
    desire_before: str,
    arousal_before: str,
    protection: str,
    orgasms: str,
    intensity: str,
    satisfaction: str,
    pleasure: str,
    reactions: str,
    emotional_state: str,
    aftercare: str,
    recovery: str,
    notes: str,
    catalog_item_id: str,
    care_product_ids: str,
) -> JournalEntry:
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Journal entry not found")
    if entry.status != "draft":
        raise ValueError("Only draft entries can be completed")

    if protection not in PROTECTION_TYPES:
        protection = "none"
    reaction_list = [x.strip() for x in reactions.split(",") if x.strip()] if reactions.strip() else None
    emotion_list = [x.strip() for x in emotional_state.split(",") if x.strip()] if emotional_state.strip() else None

    catalog_item = await resolve_catalog_item(db, catalog_item_id, user_id)
    care_uuids = await validate_care_products(db, care_product_ids, user_id)

    apply_entry_fields(
        entry,
        entry_date=entry.entry_date,
        partner_id=entry.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else activity_type,
        duration_minutes=parse_int(duration_minutes, "duration_minutes"),
        desire_before=parse_scale(desire_before, "desire_before"),
        arousal_before=parse_scale(arousal_before, "arousal_before"),
        protection=protection,
        orgasms=parse_int(orgasms, "orgasms", maximum=100),
        intensity=parse_scale(intensity, "intensity"),
        satisfaction=parse_scale(satisfaction, "satisfaction"),
        pleasure=parse_scale(pleasure, "pleasure"),
        reactions=reaction_list,
        emotional_state=emotion_list,
        aftercare=aftercare,
        recovery=parse_scale(recovery, "recovery"),
        notes=notes,
        activity_log_id=entry.activity_log_id,
        care_product_ids=care_uuids,
    )
    await db.flush()
    return entry


async def delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Journal entry not found")
    await db.delete(entry)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Partners
# ─────────────────────────────────────────────────────────────────────────────


async def create_partner(db: AsyncSession, *, user_id: uuid.UUID, name: str, notes: str) -> JournalPartner:
    name = name.strip()[:100]
    if not name:
        raise ValueError("Name is required")
    partner = JournalPartner(user_id=user_id, name=name, notes=(notes or "").strip() or None)
    db.add(partner)
    await db.flush()
    return partner


async def delete_partner(db: AsyncSession, user_id: uuid.UUID, partner_id: uuid.UUID) -> None:
    partner = (
        await db.execute(
            select(JournalPartner).where(JournalPartner.id == partner_id, JournalPartner.user_id == user_id)
        )
    ).scalar_one_or_none()
    if partner is None:
        raise NotFoundError("Partner not found")
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user_id, JournalEntry.partner_id == partner_id)
            )
        )
        .scalars()
        .all()
    )
    for e in entries:
        e.partner_id = None
    await db.delete(partner)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Media
# ─────────────────────────────────────────────────────────────────────────────


async def attach_entry_media(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    file_info: dict,
    caption: str,
) -> MediaAsset:
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Journal entry not found")
    asset = MediaAsset(
        owner_id=user_id,
        owner_type="journal_entry",
        owner_ref_id=entry.id,
        state="ready",
        file_path=file_info["file_path"],
        thumbnail_path=file_info["thumbnail_path"],
        original_filename=file_info["original_filename"],
        mime_type=file_info["mime_type"],
        file_size_bytes=file_info["file_size_bytes"],
        sha256_hex=file_info["sha256_hex"],
        width=file_info["width"],
        height=file_info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)
    await db.flush()
    return asset


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — queries
# ─────────────────────────────────────────────────────────────────────────────


async def json_journal_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user_id).order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    partners = (
        (
            await db.execute(
                select(JournalPartner).where(JournalPartner.user_id == user_id).order_by(JournalPartner.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": len(entries),
        "pending": sum(1 for e in entries if e.status == "draft"),
        "entries": [entry_json(e) for e in entries[:50]],
        "partners": [
            {
                "id": str(p.id),
                "name": p.name,
                "notes": p.notes,
            }
            for p in partners
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def json_create_entry(db: AsyncSession, user_id: uuid.UUID, body: EntryBody) -> JournalEntry:
    if body.partner_id is not None:
        partner = (
            await db.execute(
                select(JournalPartner).where(JournalPartner.id == body.partner_id, JournalPartner.user_id == user_id)
            )
        ).scalar_one_or_none()
        if partner is None:
            raise NotFoundError("Partner not found")
    protection = body.protection if body.protection in PROTECTION_TYPES else "none"
    aid = await validate_activity_log(db, body.activity_log_id, user_id)
    catalog_item = await resolve_catalog_item(db, body.catalog_item_id, user_id)
    care_uuids = await validate_care_products(db, body.care_product_ids, user_id)

    cycle_ph, cycle_day = await cycle_snapshot(db, user_id, body.entry_date)

    entry = JournalEntry(
        user_id=user_id,
        entry_date=body.entry_date,
        status="completed",
        source="activity" if aid else "manual",
        cycle_phase=cycle_ph,
        cycle_day=cycle_day,
    )
    apply_entry_fields(
        entry,
        entry_date=body.entry_date,
        partner_id=body.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else body.activity_type or "",
        duration_minutes=body.duration_minutes,
        desire_before=body.desire_before,
        arousal_before=body.arousal_before,
        protection=protection,
        orgasms=body.orgasms,
        intensity=body.intensity,
        satisfaction=body.satisfaction,
        pleasure=body.pleasure,
        reactions=body.reactions,
        emotional_state=body.emotional_state,
        aftercare=body.aftercare or "",
        recovery=body.recovery,
        notes=body.notes or "",
        activity_log_id=aid,
        care_product_ids=care_uuids,
    )
    db.add(entry)
    await db.flush()
    return entry


async def json_complete_entry(
    db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID, body: CompleteBody
) -> JournalEntry:
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Journal entry not found")
    if entry.status != "draft":
        raise ValueError("Only draft entries can be completed")

    protection = body.protection if body.protection in PROTECTION_TYPES else "none"
    catalog_item = await resolve_catalog_item(db, body.catalog_item_id, user_id)
    care_uuids = await validate_care_products(db, body.care_product_ids, user_id)
    apply_entry_fields(
        entry,
        entry_date=entry.entry_date,
        partner_id=entry.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else body.activity_type or "",
        duration_minutes=body.duration_minutes,
        desire_before=body.desire_before,
        arousal_before=body.arousal_before,
        protection=protection,
        orgasms=body.orgasms,
        intensity=body.intensity,
        satisfaction=body.satisfaction,
        pleasure=body.pleasure,
        reactions=body.reactions,
        emotional_state=body.emotional_state,
        aftercare=body.aftercare or "",
        recovery=body.recovery,
        notes=body.notes or "",
        activity_log_id=entry.activity_log_id,
        care_product_ids=care_uuids,
    )
    await db.flush()
    return entry


async def json_create_partner(db: AsyncSession, user_id: uuid.UUID, body: PartnerBody) -> JournalPartner:
    return await create_partner(db, user_id=user_id, name=body.name, notes=body.notes or "")


async def json_delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    await delete_entry(db, user_id, entry_id)


async def json_delete_partner(db: AsyncSession, user_id: uuid.UUID, partner_id: uuid.UUID) -> None:
    await delete_partner(db, user_id, partner_id)


async def json_analyze_partner_dynamics(db, user_id, partner_id, llm_config, *, locale: str):
    from app.llm.pipeline.journal_consultant import analyze_partner_dynamics

    return await analyze_partner_dynamics(db, user_id, partner_id, llm_config, locale=locale)
