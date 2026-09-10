"""Sexual Journal — Page context builder."""

from __future__ import annotations

from sqlalchemy import select
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

from app.services.journal.entry_fields import entry_view
from app.services.journal.summary import activity_title_map, media_map


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
