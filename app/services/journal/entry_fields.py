"""Sexual Journal — Entry field application and serializers."""

from __future__ import annotations

import uuid
from datetime import date

from app.models.journal import JournalEntry


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
