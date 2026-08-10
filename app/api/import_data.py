"""Import/Export module: CSV/JSON templates, upload, API for external services, full export."""

import csv
import io
import json
import logging
import uuid
from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.auth import get_optional_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.points import PointsProfile, PointsTransaction
from app.models.training import TrainingDay
from app.models.user import User
from app.schemas.points_v2 import ImportPayload
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])


# ── Template definitions (8 types) ──

TEMPLATES: dict[str, dict] = {
    "measurements": {
        "label": "Body Measurements",
        "csv_headers": "date,time_of_day,weight,chest,under_chest,waist,hips,thigh,notes",
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
        "label": "Inventory / Shopping List",
        "csv_headers": "category,name,description,quantity,quantity_needed,is_shopping_list,status,priority",
        "example_csv": ("clothing,Black stockings 40 den,,3,5,true,need,2\nequipment,Rope 6mm 20m,,4,7,true,need,5"),
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
        "label": "Entities (Tasks)",
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
                                    "redemption": {"type": "clothespins", "duration_min": 10},
                                }
                            ],
                        },
                    },
                }
            ],
        },
    },
    "schedule": {
        "label": "Schedule Rules",
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
    "points_transactions": {
        "label": "Points Transactions",
        "csv_headers": "amount,transaction_type,reason,entity_code,created_at",
        "example_csv": (
            "50,earn,Daily plank completed,Morning plank,2024-01-15T08:00:00\n"
            "-5,penalty,Missed task,Clothespins,2024-01-15T09:00:00"
        ),
        "json_schema": {
            "import_type": "points_transactions",
            "data": [
                {
                    "amount": 50,
                    "transaction_type": "earn",
                    "reason": "Daily plank completed",
                    "entity_name": "Morning plank",
                    "created_at": "2024-01-15T08:00:00",
                }
            ],
        },
    },
    "training_days": {
        "label": "Training Days",
        "csv_headers": "target_date,status,plan_summary,analysis_summary",
        "example_csv": "2024-01-15,completed,Morning routine + evening punishment,Good progress today",
        "json_schema": {
            "import_type": "training_days",
            "data": [
                {
                    "target_date": "2024-01-15",
                    "status": "completed",
                    "plan_summary": "Morning routine + evening punishment",
                    "analysis_summary": "Good progress today",
                }
            ],
        },
    },
    "activity_logs": {
        "label": "Activity Logs",
        "csv_headers": "status,entity_code,selected_entity_name,completed_at",
        "example_csv": "completed,Morning plank,Morning plank,2024-01-15T08:05:00",
        "json_schema": {
            "import_type": "activity_logs",
            "data": [
                {
                    "status": "completed",
                    "entity_name": "Morning plank",
                    "selected_entity_name": "Morning plank",
                    "created_at": "2024-01-15T08:05:00",
                }
            ],
        },
    },
    "points_profiles": {
        "label": "Points Profiles",
        "csv_headers": "name,is_default",
        "example_csv": "Hardcore mode,false",
        "json_schema": {
            "import_type": "points_profiles",
            "data": [
                {
                    "name": "Hardcore mode",
                    "is_default": False,
                    "config": {
                        "points": {"base": 10, "max_per_day": 100},
                        "penalties": {
                            "enabled": True,
                            "escalation": True,
                            "levels": [
                                {"level": 1, "deduction": 10, "condition": "missed"},
                            ],
                        },
                        "bonuses": [],
                        "thresholds": {"negative": -200, "warning": 0, "good": 200},
                    },
                }
            ],
        },
    },
}

# ── Exportable types mapping ──

EXPORT_TYPES: dict[str, dict] = {
    "measurements": {"model": BodyMeasurement, "csv_headers": TEMPLATES["measurements"]["csv_headers"].split(",")},
    "inventory": {"model": InventoryItem, "csv_headers": TEMPLATES["inventory"]["csv_headers"].split(",")},
    "schedule": {"model": ScheduleRule, "csv_headers": TEMPLATES["schedule"]["csv_headers"].split(",")},
    "entities": {"model": Entity, "csv_headers": TEMPLATES["entities"]["csv_headers"].split(",")},
    "points_transactions": {
        "model": PointsTransaction,
        "csv_headers": TEMPLATES["points_transactions"]["csv_headers"].split(","),
    },
    "training_days": {"model": TrainingDay, "csv_headers": TEMPLATES["training_days"]["csv_headers"].split(",")},
    "activity_logs": {"model": ActivityLog, "csv_headers": TEMPLATES["activity_logs"]["csv_headers"].split(",")},
}


# ═══════════════════════════════════════════════════════════
# Template endpoints
# ═══════════════════════════════════════════════════════════


@router.get("/templates")
async def list_templates():
    """List all available import templates with labels."""
    return {
        k: {
            "label": v["label"],
            "csv_headers": v["csv_headers"],
            "has_json_schema": bool(v.get("json_schema")),
        }
        for k, v in TEMPLATES.items()
    }


@router.get("/template/{template_type}")
async def get_template(
    template_type: str,
    format: str = Query(default="csv"),
):
    """Download a template for external services (CSV or JSON)."""
    if template_type not in TEMPLATES:
        raise HTTPException(404, f"Unknown template: {template_type}. Available: {list(TEMPLATES)}")

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


# ═══════════════════════════════════════════════════════════
# Web UI page
# ═══════════════════════════════════════════════════════════


@router.get("", response_class=HTMLResponse)
async def import_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Import/Export management page."""
    if not user:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/auth/login", status_code=303)
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="import_data.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "templates": {k: {"label": v["label"], "csv_headers": v["csv_headers"]} for k, v in TEMPLATES.items()},
            "export_types": list(EXPORT_TYPES),
            # Used in clipboard URL — derived from request, NOT hardcoded localhost.
            "app_url": str(request.url_root).rstrip("/"),
        },
    )


# ═══════════════════════════════════════════════════════════
# Upload endpoint
# ═══════════════════════════════════════════════════════════


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a CSV or JSON file for import. Auto-detects type from headers."""
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv"):
        return await _import_csv(content.decode("utf-8"), db, user)
    elif filename.endswith(".json"):
        return await _import_json(json.loads(content.decode("utf-8")), db, user)
    else:
        raise HTTPException(400, "Unsupported file format. Use .csv or .json")


# ═══════════════════════════════════════════════════════════
# API push endpoint for external services
# ═══════════════════════════════════════════════════════════


@router.post("/api")
async def api_push(
    payload: ImportPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """API endpoint for external services to push data (JSON)."""
    return await _import_json(
        {"import_type": payload.import_type, "data": payload.data},
        db,
        user,
        mode=payload.mode,
    )


# ═══════════════════════════════════════════════════════════
# Import logic
# ═══════════════════════════════════════════════════════════


async def _import_csv(content: str, db: AsyncSession, user: User) -> dict:
    """Parse CSV and auto-detect import type from headers."""
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return {"status": "ok", "imported": 0, "message": "Empty file"}

    headers = set(rows[0].keys())

    if "weight" in headers or "measured_date" in headers:
        return await _import_measurements(rows, db, user)
    elif "category" in headers and "name" in headers and "quantity" in headers:
        return await _import_inventory(rows, db, user)
    elif "real_name" in headers and "category" in headers:
        return await _import_entities(rows, db, user)
    elif "day_of_week" in headers and "start_time" in headers:
        return await _import_schedule(rows, db, user)
    elif "transaction_type" in headers and "amount" in headers:
        return await _import_points_transactions(rows, db, user)
    elif "target_date" in headers and "status" in headers:
        return await _import_training_days(rows, db, user)
    elif "status" in headers and "selected_entity_name" in headers:
        return await _import_activity_logs(rows, db, user)
    elif "name" in headers and "is_default" in headers:
        return await _import_points_profiles(rows, db, user)
    else:
        raise HTTPException(400, f"Cannot auto-detect import type from CSV headers: {sorted(headers)}")


async def _import_json(data: dict, db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    """Import from JSON payload."""
    import_type = data.get("import_type", "")
    rows = data.get("data", [])

    handlers: dict[str, Any] = {
        "measurements": _import_measurements,
        "inventory": _import_inventory,
        "entities": _import_entities,
        "schedule": _import_schedule,
        "points_transactions": _import_points_transactions,
        "training_days": _import_training_days,
        "activity_logs": _import_activity_logs,
        "points_profiles": _import_points_profiles,
    }

    handler = handlers.get(import_type)
    if not handler:
        raise HTTPException(400, f"Unknown import_type: {import_type}. Available: {list(handlers)}")

    return await handler(rows, db, user, mode)


# ── Individual import handlers ──


async def _import_measurements(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
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
            logger.warning(f"Skip measurement row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_inventory(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
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
            logger.warning(f"Skip inventory row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_entities(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            gc = row.get("gamification_config")
            if isinstance(gc, dict):
                pass
            elif isinstance(gc, str) and gc:
                gc = json.loads(gc)
            else:
                gc = None

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
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_schedule(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
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
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_points_transactions(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            entity_id = None
            entity_name = row.get("entity_name") or row.get("entity_code")
            if entity_name:
                e_result = await db.execute(select(Entity.id).where(Entity.real_name == str(entity_name)).limit(1))
                e_row = e_result.first()
                if e_row:
                    entity_id = e_row[0]

            created_at = datetime.now()
            if row.get("created_at"):
                created_at = datetime.fromisoformat(str(row["created_at"]))

            txn = PointsTransaction(
                user_id=user.id,
                amount=int(row.get("amount", 0)),
                transaction_type=str(row.get("transaction_type", "earn")),
                reason=str(row.get("reason", "")) or None,
                entity_id=entity_id,
                created_at=created_at,
            )
            db.add(txn)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip points_transaction row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_training_days(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            td = TrainingDay(
                user_id=user.id,
                target_date=date.fromisoformat(str(row.get("target_date", date.today().isoformat()))),
                status=str(row.get("status", "planned")),
                plan_summary=str(row.get("plan_summary", "")) or None,
                analysis_summary=str(row.get("analysis_summary", "")) or None,
            )
            db.add(td)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip training_day row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_activity_logs(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            entity_id = None
            entity_name = row.get("entity_name") or row.get("entity_code")
            if entity_name:
                e_result = await db.execute(select(Entity.id).where(Entity.real_name == str(entity_name)).limit(1))
                e_row = e_result.first()
                if e_row:
                    entity_id = e_row[0]

            created_at = datetime.now()
            if row.get("created_at"):
                created_at = datetime.fromisoformat(str(row["created_at"]))

            completed_at = None
            if row.get("completed_at"):
                completed_at = datetime.fromisoformat(str(row["completed_at"]))

            log = ActivityLog(
                user_id=user.id,
                entity_id=entity_id,
                status=str(row.get("status", "created")),
                selected_entity_name=str(row.get("selected_entity_name", "")),
                created_at=created_at,
                completed_at=completed_at,
            )
            db.add(log)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip activity_log row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_points_profiles(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            config = row.get("config", {})
            if isinstance(config, str) and config:
                config = json.loads(config)

            profile = PointsProfile(
                user_id=user.id,
                name=str(row.get("name", "Unnamed Profile")),
                config=config,
                is_default=str(row.get("is_default", "false")).lower() == "true",
            )
            db.add(profile)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip points_profile row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


# ═══════════════════════════════════════════════════════════
# Export endpoints
# ═══════════════════════════════════════════════════════════


@router.get("/export/full")
async def export_full(
    format: str = Query(default="json"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full backup: export ALL user data as a single JSON."""
    full: dict[str, Any] = {
        "exported_at": datetime.now().isoformat(),
        "version": "0.5.0",
        "user": {
            "email": user.email,
            "locale": user.locale,
            "theme": user.theme,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }

    for etype, info in EXPORT_TYPES.items():
        model = info["model"]
        # Entity uses owner_id, not user_id
        user_col = getattr(model, "user_id", None) or getattr(model, "owner_id", None)
        if user_col is None:
            continue
        result = await db.execute(
            select(model).where(user_col == user.id).order_by(model.created_at.desc()).limit(5000)
        )
        rows = result.scalars().all()
        full[etype] = {"count": len(rows), "data": [_model_to_dict(r) for r in rows]}

    # Also add progress
    from app.gamification.handler import get_or_create_progress

    progress = await get_or_create_progress(db, user.id)
    full["progress"] = {
        "xp": progress.xp,
        "level": progress.level,
        "current_streak": progress.current_streak,
        "longest_streak": progress.longest_streak,
        "total_completed": progress.total_completed,
        "total_interrupted": progress.total_interrupted,
    }

    if format == "csv":
        raise HTTPException(400, "Full export only supports JSON format")
    return JSONResponse(full)


@router.get("/export/{export_type}")
async def export_type(
    export_type: str,
    format: str = Query(default="json"),
    limit: int = Query(default=10000, ge=1, le=100000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export user data by type as JSON or CSV."""
    if export_type not in EXPORT_TYPES:
        raise HTTPException(404, f"Unknown export type: {export_type}. Available: {list(EXPORT_TYPES)}")

    info = EXPORT_TYPES[export_type]
    model_cls = info["model"]
    # Entity uses owner_id, others use user_id
    user_col = getattr(model_cls, "user_id", None) or getattr(model_cls, "owner_id", None)

    result = await db.execute(
        select(model_cls).where(user_col == user.id).order_by(model_cls.created_at.desc()).limit(limit)
    )
    rows = result.scalars().all()

    if format == "csv":
        return _rows_to_csv(rows, info["csv_headers"], export_type)
    else:
        data = [_model_to_dict(r) for r in rows]
        return JSONResponse({"export_type": export_type, "count": len(data), "data": data})


def _model_to_dict(obj: Any) -> dict:
    """Convert a SQLAlchemy model instance to a JSON-safe dict."""
    data: dict = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key)
        if isinstance(val, (datetime, date, time)):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        data[col.key] = val
    return data


def _rows_to_csv(rows: list, headers: list[str], export_type: str) -> PlainTextResponse:
    """Convert model rows to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for row in rows:
        values = []
        for h in headers:
            val = getattr(row, h, None)
            if isinstance(val, (datetime, date, time)):
                val = val.isoformat()
            elif isinstance(val, uuid.UUID):
                val = str(val)
            elif isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            values.append(str(val) if val is not None else "")
        writer.writerow(values)

    return PlainTextResponse(
        output.getvalue(),
        headers={"Content-Disposition": f"attachment; filename={export_type}_export.csv"},
    )


# ── Helpers ──


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
