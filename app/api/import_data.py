"""Import module: CSV/JSON templates, upload, API for external services."""

import csv
import io
import json
import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.entity import Entity
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.user import User
from app.schemas.points_v2 import (
    ImportPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])


# ── Template generation ──


TEMPLATES = {
    "measurements": {
        "csv_headers": ("date,time_of_day,weight,chest,under_chest,waist,hips,thigh,notes"),
        "example_csv": ("2024-01-15,morning,98.5,112,100,100,106,61,\n2024-01-15,evening,99.0,,,,,,"),
        "json_schema": {
            "import_type": "measurements",
            "data": [
                {
                    "measured_date": "2024-01-15",
                    "time_of_day": "morning",
                    "weight": 98.5,
                    "chest": 112.0,
                    "under_chest": 100.0,
                    "waist": 100.0,
                    "hips": 106.0,
                    "thigh": 61.0,
                }
            ],
        },
    },
    "inventory": {
        "csv_headers": "category,name,description,quantity,quantity_needed,is_shopping_list,status,priority",
        "example_csv": "clothing,Black stockings 40 den,,3,5,true,need,2\nequipment,Rope 6mm 20m,,4,7,true,need,5",
        "json_schema": {
            "import_type": "inventory",
            "data": [
                {
                    "category": "clothing",
                    "name": "Black stockings 40 den",
                    "quantity": 3,
                    "quantity_needed": 5,
                    "is_shopping_list": True,
                    "status": "need",
                    "priority": 2,
                }
            ],
        },
    },
    "entities": {
        "csv_headers": (
            "type,real_name,category,level,parent_code,tags,is_public,points_base,penalty_enabled,penalty_levels"
        ),
        "example_csv": ("one_time,Morning plank,exercise,1,,fitness,true,10,true,missed:5:clothespins:10"),
        "json_schema": {
            "import_type": "entities",
            "data": [
                {
                    "type": "one_time",
                    "real_name": "Morning plank",
                    "category": "exercise",
                    "level": 1,
                    "is_public": False,
                    "gamification_config": {
                        "points": {"base": 10},
                        "penalties": {
                            "enabled": True,
                            "levels": [
                                {
                                    "level": 1,
                                    "deduction": 5,
                                    "condition": "missed",
                                    "redemption": {
                                        "type": "clothespins",
                                        "duration_min": 10,
                                    },
                                }
                            ],
                        },
                    },
                }
            ],
        },
    },
    "schedule": {
        "csv_headers": "entity_code,day_of_week,start_time,end_time,task_type,recurring,notes",
        "example_csv": "MORNING_PLANK,7,06:35,06:45,mandatory,true,Morning exercise",
        "json_schema": {
            "import_type": "schedule",
            "data": [
                {
                    "entity_name": "Morning plank",
                    "day_of_week": 7,
                    "start_time": "06:35",
                    "end_time": "06:45",
                    "task_type": "mandatory",
                }
            ],
        },
    },
}


@router.get("/templates")
async def list_templates():
    """List available import templates."""
    return {
        k: {"csv_headers": v["csv_headers"], "has_json_schema": bool(v.get("json_schema"))}
        for k, v in TEMPLATES.items()
    }


@router.get("/template/{template_type}")
async def get_template(
    template_type: str,
    format: str = Query(default="csv"),
):
    """Get a template for a specific data type."""
    if template_type not in TEMPLATES:
        raise HTTPException(404, f"Unknown template: {template_type}")

    tmpl = TEMPLATES[template_type]

    if format == "csv":
        return PlainTextResponse(
            tmpl["csv_headers"] + "\n" + tmpl.get("example_csv", ""),
            headers={"Content-Disposition": f"attachment; filename={template_type}_template.csv"},
        )
    elif format == "json":
        return JSONResponse(tmpl.get("json_schema", {}))
    else:
        raise HTTPException(400, "Format must be csv or json")


# ── Upload endpoint ──


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a CSV or JSON file for import."""
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv"):
        return await _import_csv(content.decode("utf-8"), filename.replace(".csv", ""), db, user)
    elif filename.endswith(".json"):
        return await _import_json(json.loads(content.decode("utf-8")), db, user)
    else:
        raise HTTPException(400, "Unsupported file format. Use .csv or .json")


# ── API push endpoint for external services ──


@router.post("/api")
async def api_push(
    payload: ImportPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """API endpoint for external services to push data."""
    return await _import_json(
        {"import_type": payload.import_type, "data": payload.data},
        db,
        user,
        mode=payload.mode,
    )


# ── Import logic ──


async def _import_csv(
    content: str,
    import_type: str,
    db: AsyncSession,
    user: User,
) -> dict:
    """Parse CSV and import based on type detection."""
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return {"status": "ok", "imported": 0, "message": "Empty file"}

    # Auto-detect type from headers
    if "weight" in rows[0] or "measured_date" in rows[0]:
        return await _import_measurements(rows, db, user)
    elif "category" in rows[0] and "name" in rows[0] and "quantity" in rows[0]:
        return await _import_inventory(rows, db, user)
    elif "real_name" in rows[0] and "category" in rows[0]:
        return await _import_entities(rows, db, user)
    elif "day_of_week" in rows[0] and "start_time" in rows[0]:
        return await _import_schedule(rows, db, user)
    else:
        raise HTTPException(400, f"Cannot auto-detect import type from CSV headers: {list(rows[0].keys())}")


async def _import_json(
    data: dict,
    db: AsyncSession,
    user: User,
    mode: str = "upsert",
) -> dict:
    """Import from JSON payload."""
    import_type = data.get("import_type", "")
    rows = data.get("data", [])

    if import_type == "measurements":
        return await _import_measurements(rows, db, user, mode)
    elif import_type == "inventory":
        return await _import_inventory(rows, db, user, mode)
    elif import_type == "entities":
        return await _import_entities(rows, db, user, mode)
    elif import_type == "schedule":
        return await _import_schedule(rows, db, user, mode)
    else:
        raise HTTPException(400, f"Unknown import_type: {import_type}")


async def _import_measurements(
    rows: list[dict],
    db: AsyncSession,
    user: User,
    mode: str = "upsert",
) -> dict:
    imported = 0
    for row in rows:
        try:
            d = {
                "measured_date": date.fromisoformat(str(row.get("measured_date", row.get("date", "")))),
                "time_of_day": str(row.get("time_of_day", "morning")),
                "weight": _float_or_none(row.get("weight")),
                "chest": _float_or_none(row.get("chest")),
                "under_chest": _float_or_none(row.get("under_chest")),
                "waist": _float_or_none(row.get("waist")),
                "hips": _float_or_none(row.get("hips")),
                "thigh": _float_or_none(row.get("thigh")),
                "notes": str(row.get("notes", "")) or None,
            }
            # Upsert
            result = await db.execute(
                select(BodyMeasurement).where(
                    BodyMeasurement.user_id == user.id,
                    BodyMeasurement.measured_date == d["measured_date"],
                    BodyMeasurement.time_of_day == d["time_of_day"],
                )
            )
            existing = result.scalar_one_or_none()
            if existing and mode != "insert":
                for k, v in d.items():
                    setattr(existing, k, v)
            else:
                db.add(BodyMeasurement(user_id=user.id, **d))
            imported += 1
        except (ValueError, KeyError) as e:
            logger.warning(f"Skip row: {e}")
    await db.commit()
    return {"status": "ok", "imported": imported}


async def _import_inventory(
    rows: list[dict],
    db: AsyncSession,
    user: User,
    mode: str = "upsert",
) -> dict:
    imported = 0
    for row in rows:
        try:
            item = InventoryItem(
                user_id=user.id,
                category=str(row.get("category", "other")),
                name=str(row.get("name", "")),
                description=str(row.get("description", "")) or None,
                quantity=int(row.get("quantity", 1)),
                quantity_needed=int(row.get("quantity_needed", 1)),
                is_shopping_list=str(row.get("is_shopping_list", "false")).lower() == "true",
                status=str(row.get("status", "need")),
                priority=int(row.get("priority", 0)),
            )
            db.add(item)
            imported += 1
        except (ValueError, KeyError) as e:
            logger.warning(f"Skip row: {e}")
    await db.commit()
    return {"status": "ok", "imported": imported}


async def _import_entities(
    rows: list[dict],
    db: AsyncSession,
    user: User,
    mode: str = "upsert",
) -> dict:
    imported = 0
    for row in rows:
        try:
            gc = row.get("gamification_config")
            if isinstance(gc, dict):
                gc = gc  # Already parsed
            elif isinstance(gc, str) and gc:
                gc = json.loads(gc)
            else:
                gc = None

            # Parse parent_code if present
            parent_id = None
            parent_code = row.get("parent_code")
            if parent_code:
                p_result = await db.execute(select(Entity.id).where(Entity.real_name == str(parent_code)).limit(1))
                p_row = p_result.first()
                if p_row:
                    parent_id = p_row[0]

            tags = row.get("tags")
            if isinstance(tags, str) and tags:
                tags = [t.strip() for t in tags.split(",")]

            entity = Entity(
                type=str(row.get("type", "one_time")),
                real_name=str(row.get("real_name", "")),
                category=str(row.get("category", "general")),
                level=int(row.get("level", 1)),
                parent_id=parent_id,
                tags=tags,
                is_public=str(row.get("is_public", "false")).lower() == "true",
                author_id=user.id,
                owner_id=user.id,
                gamification_config=gc,
            )
            db.add(entity)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip entity row: {e}")
    await db.commit()
    return {"status": "ok", "imported": imported}


async def _import_schedule(
    rows: list[dict],
    db: AsyncSession,
    user: User,
    mode: str = "upsert",
) -> dict:
    imported = 0
    for row in rows:
        try:
            entity_id = None
            entity_name = row.get("entity_name") or row.get("entity_code")
            if entity_name:
                e_result = await db.execute(select(Entity.id).where(Entity.real_name == str(entity_name)).limit(1))
                e_row = e_result.first()
                if e_row:
                    entity_id = e_row[0]

            start_time = datetime.strptime(str(row.get("start_time", "00:00")), "%H:%M").time()
            end_time = None
            if row.get("end_time"):
                end_time = datetime.strptime(str(row["end_time"]), "%H:%M").time()

            rule = ScheduleRule(
                user_id=user.id,
                entity_id=entity_id,
                day_of_week=int(row.get("day_of_week", 0)),
                start_time=start_time,
                end_time=end_time,
                task_type=str(row.get("task_type", "mandatory")),
                recurring=str(row.get("recurring", "true")).lower() == "true",
                notes=str(row.get("notes", "")) or None,
            )
            db.add(rule)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip schedule row: {e}")
    await db.commit()
    return {"status": "ok", "imported": imported}


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
