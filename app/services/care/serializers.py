"""Personal Care — Serializers (views and JSON)."""

from __future__ import annotations

from datetime import timedelta

from app.models.care import CareCourse, CareEntry, CareProduct, CareRoutine
from app.timeutils import local_today


def product_view(
    p: CareProduct,
    usage_by_product: dict[str, int],
    inventory_names: dict[str, dict],
    catalog_names: dict[str, str] | None = None,
) -> dict:
    inv = inventory_names.get(str(p.inventory_item_id)) if p.inventory_item_id else None
    today = local_today()
    low_stock = p.quantity is not None and 0 < p.quantity <= 1
    expiring = p.expiry_date is not None and p.expiry_date <= today + timedelta(days=30)
    return {
        "id": str(p.id),
        "name": p.name,
        "category": p.category,
        "brand": p.brand,
        "notes": p.notes,
        "quantity": p.quantity,
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "low_stock": low_stock,
        "expiring": expiring,
        "inventory_item_id": str(p.inventory_item_id) if p.inventory_item_id else None,
        "inventory_name": inv["name"] if inv else None,
        "inventory_status": inv["status"] if inv else None,
        "catalog_item_id": str(p.catalog_item_id) if p.catalog_item_id else None,
        "catalog_name": (catalog_names or {}).get(str(p.catalog_item_id)) if p.catalog_item_id else None,
        "usage_count": usage_by_product.get(str(p.id), 0),
    }


def entry_view(
    e: CareEntry,
    routine_names: dict[str, str],
    product_ids_by_entry: dict[str, list[str]] | None = None,
) -> dict:
    product_ids = (product_ids_by_entry or {}).get(str(e.id), [])
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "routine_name": routine_names.get(str(e.routine_id)) if e.routine_id else None,
        "place_name": e.place_name,
        "place_address": e.place_address,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
        "product_ids": product_ids,
    }


def routine_json(r: CareRoutine) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "catalog_item_id": str(r.catalog_item_id) if r.catalog_item_id else None,
        "area": r.area,
        "kind": r.kind,
        "place_name": r.place_name,
        "place_address": r.place_address,
        "frequency_days": r.frequency_days,
        "notes": r.notes,
        "product_ids": [str(pr.id) for pr in r.products],
    }


def product_json(p: CareProduct) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "category": p.category,
        "brand": p.brand,
        "notes": p.notes,
        "quantity": p.quantity,
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "inventory_item_id": str(p.inventory_item_id) if p.inventory_item_id else None,
        "catalog_item_id": str(p.catalog_item_id) if p.catalog_item_id else None,
    }


def entry_json(e: CareEntry, product_ids_by_entry: dict[str, list[str]] | None = None) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "place_name": e.place_name,
        "place_address": e.place_address,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
        "product_ids": (product_ids_by_entry or {}).get(str(e.id), []),
    }


def course_json(c: CareCourse) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "catalog_item_id": str(c.catalog_item_id) if c.catalog_item_id else None,
        "area": c.area,
        "place_name": c.place_name,
        "place_address": c.place_address,
        "total_sessions": c.total_sessions,
        "interval_days": c.interval_days,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "notes": c.notes,
        "status": c.status,
        "sessions": [
            {
                "id": str(s.id),
                "session_number": s.session_number,
                "scheduled_date": s.scheduled_date.isoformat(),
                "status": s.status,
                "entry_id": str(s.entry_id) if s.entry_id else None,
                "notes": s.notes,
            }
            for s in sorted(c.sessions, key=lambda s: s.session_number)
        ],
    }
