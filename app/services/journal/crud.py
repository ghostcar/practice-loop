"""Sexual Journal — CRUD operations."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import (
    PROTECTION_TYPES,
    JournalEntry,
    JournalPartner,
)
from app.models.media import MediaAsset
from app.services.errors import NotFoundError

from app.services.journal.cycle import cycle_snapshot
from app.services.journal.entry_fields import apply_entry_fields, entry_json
from app.services.journal.helpers import (
    parse_int,
    parse_scale,
    resolve_catalog_item,
    validate_activity_log,
    validate_care_products,
    validate_partner_id,
    validate_partner,
)
from app.services.journal.schemas import EntryBody, CompleteBody, PartnerBody


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
# JSON API — CRUD wrappers
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
