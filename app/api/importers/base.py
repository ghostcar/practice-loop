"""Shared import pipeline — CSV/JSON parsing, type dispatch, row helpers.

REFACTORING.md step 2: split from app/api/import_data.py. Individual importers
live in sibling modules; they are resolved lazily here to avoid an import cycle
(importer modules import ``_float_or_none`` from this module).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)


def _json_handlers() -> dict[str, Any]:
    """Resolve JSON import handlers lazily (avoids cycle: base ← importers → base)."""
    from app.api.importers.activity_logs import _import_activity_logs
    from app.api.importers.body_parts import _import_body_parts
    from app.api.importers.categories import _import_inventory_categories
    from app.api.importers.entities import _import_entities
    from app.api.importers.inventory import _import_inventory
    from app.api.importers.locations import _import_locations
    from app.api.importers.measurements import _import_measurements
    from app.api.importers.points import _import_points_profiles, _import_points_transactions
    from app.api.importers.schedule import _import_schedule
    from app.api.importers.training import _import_training_days

    return {
        "measurements": _import_measurements,
        "inventory": _import_inventory,
        "entities": _import_entities,
        "schedule": _import_schedule,
        "points_transactions": _import_points_transactions,
        "training_days": _import_training_days,
        "activity_logs": _import_activity_logs,
        "points_profiles": _import_points_profiles,
        "body_parts": _import_body_parts,
        "locations": _import_locations,
        "inventory_categories": _import_inventory_categories,
    }


async def _import_csv(content: str, db: AsyncSession, user: User) -> dict:
    """Parse CSV and auto-detect import type from headers."""
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return {"status": "ok", "imported": 0, "message": "Empty file"}

    headers = set(rows[0].keys())

    if "weight" in headers or "measured_date" in headers:
        from app.api.importers.measurements import _import_measurements

        return await _import_measurements(rows, db, user)
    elif "category" in headers and "name" in headers and "quantity" in headers:
        from app.api.importers.inventory import _import_inventory

        return await _import_inventory(rows, db, user)
    elif "real_name" in headers and "category" in headers:
        from app.api.importers.entities import _import_entities

        return await _import_entities(rows, db, user)
    elif "day_of_week" in headers and "start_time" in headers:
        from app.api.importers.schedule import _import_schedule

        return await _import_schedule(rows, db, user)
    elif "transaction_type" in headers and "amount" in headers:
        from app.api.importers.points import _import_points_transactions

        return await _import_points_transactions(rows, db, user)
    elif "target_date" in headers and "status" in headers:
        from app.api.importers.training import _import_training_days

        return await _import_training_days(rows, db, user)
    elif "status" in headers and "selected_entity_name" in headers:
        from app.api.importers.activity_logs import _import_activity_logs

        return await _import_activity_logs(rows, db, user)
    elif "name" in headers and "is_default" in headers:
        from app.api.importers.points import _import_points_profiles

        return await _import_points_profiles(rows, db, user)
    elif "slug" in headers and "body_system" in headers:
        from app.api.importers.body_parts import _import_body_parts

        return await _import_body_parts(rows, db, user)
    elif "slug" in headers and "location_type" in headers:
        from app.api.importers.locations import _import_locations

        return await _import_locations(rows, db, user)
    elif "slug" in headers and "title" in headers and "is_shopping_list" not in headers:
        from app.api.importers.categories import _import_inventory_categories

        return await _import_inventory_categories(rows, db, user)
    else:
        raise HTTPException(400, f"Cannot auto-detect import type from CSV headers: {sorted(headers)}")


async def _import_json(data: dict, db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    """Import from JSON payload."""
    import_type = data.get("import_type", "")
    rows = data.get("data", [])

    handlers = _json_handlers()
    handler = handlers.get(import_type)
    if not handler:
        raise HTTPException(400, f"Unknown import_type: {import_type}. Available: {list(handlers)}")

    return await handler(rows, db, user, mode)


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
