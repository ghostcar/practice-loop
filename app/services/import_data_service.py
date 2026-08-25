"""Import/Export Service — business logic extracted from app.api.import_data.

Covers: template metadata, template listing/download, page context, export logic
(full + per-type), serializers. Actual per-type CSV/JSON import handlers live in
app.api.importers/* (imported by the routes).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.body_part import BodyPart
from app.models.entity import Entity
from app.models.inventory_category import InventoryCategory
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.points import PointsProfile, PointsTransaction  # noqa: F401 (PointsProfile re-export)
from app.models.task_location import TaskLocation
from app.models.training import TrainingDay
from app.version import __version__

# ═══════════════════════════════════════════════════════════
# Template metadata
# ═══════════════════════════════════════════════════════════

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
        "csv_headers": (
            "category,name,description,quantity,quantity_needed,"
            "is_shopping_list,status,priority,inventory_category_slug,inventory_status"
        ),
        "example_csv": (
            "clothing,Black stockings 40 den,,3,5,true,need,2,clothing,available\n"
            "equipment,Rope 6mm 20m,,4,7,true,need,5,bondage_equipment,available"
        ),
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
    "body_parts": {
        "label": "Body Parts (Reference)",
        "csv_headers": "slug,title_ru,title_en,body_system,is_sensitive,parent_slug",
        "example_csv": "my_custom_zone,My Zone,,general,false,",
        "json_schema": {
            "import_type": "body_parts",
            "data": [{"slug": "my_custom_zone", "title_ru": "My Zone", "body_system": "general"}],
        },
    },
    "locations": {
        "label": "Locations (Reference)",
        "csv_headers": "slug,title_ru,title_en,location_type,privacy_level,parent_slug",
        "example_csv": "my-office,Офис,Office,room,private,",
        "json_schema": {
            "import_type": "locations",
            "data": [{"slug": "my-office", "title_ru": "Офис", "location_type": "room", "privacy_level": "private"}],
        },
    },
    "inventory_categories": {
        "label": "Inventory Categories (Reference)",
        "csv_headers": "slug,title,description",
        "example_csv": "custom_tool,My Custom Tool,Personal equipment",
        "json_schema": {
            "import_type": "inventory_categories",
            "data": [{"slug": "custom_tool", "title": "My Custom Tool", "description": "Personal equipment"}],
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
    "body_parts": {"model": BodyPart, "csv_headers": TEMPLATES["body_parts"]["csv_headers"].split(",")},
    "locations": {"model": TaskLocation, "csv_headers": TEMPLATES["locations"]["csv_headers"].split(",")},
    "inventory_categories": {
        "model": InventoryCategory,
        "csv_headers": TEMPLATES["inventory_categories"]["csv_headers"].split(","),
    },
}


# ═══════════════════════════════════════════════════════════
# Template endpoints (logic)
# ═══════════════════════════════════════════════════════════


def list_templates_meta() -> dict:
    """List all available import templates with labels."""
    return {
        k: {
            "label": v["label"],
            "csv_headers": v["csv_headers"],
            "has_json_schema": bool(v.get("json_schema")),
        }
        for k, v in TEMPLATES.items()
    }


def get_template_download(template_type: str, format: str = "csv"):
    """Build CSV/JSON template download response."""
    if template_type not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_type}. Available: {list(TEMPLATES)}")

    tmpl = TEMPLATES[template_type]

    if format == "csv":
        return PlainTextResponse(
            tmpl["csv_headers"] + "\n" + tmpl.get("example_csv", ""),
            headers={"Content-Disposition": f"attachment; filename={template_type}_template.csv"},
        )
    elif format == "json":
        return JSONResponse(tmpl.get("json_schema", {}))
    else:
        raise ValueError("Format must be csv or json")


# ═══════════════════════════════════════════════════════════
# Page context
# ═══════════════════════════════════════════════════════════


def get_import_page_context(app_url: str) -> dict:
    """Build template context for the import/export management page."""
    return {
        "templates": {k: {"label": v["label"], "csv_headers": v["csv_headers"]} for k, v in TEMPLATES.items()},
        "export_types": list(EXPORT_TYPES),
        "app_url": app_url,
    }


# ═══════════════════════════════════════════════════════════
# Export helpers
# ═══════════════════════════════════════════════════════════


def model_to_dict(obj: Any) -> dict:
    """Convert a SQLAlchemy model instance to a JSON-safe dict."""
    data: dict = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key)
        if isinstance(val, datetime | date | time):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        data[col.key] = val
    return data


def rows_to_csv(rows: list, headers: list[str], export_type: str) -> PlainTextResponse:
    """Convert model rows to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for row in rows:
        values = []
        for h in headers:
            val = getattr(row, h, None)
            if isinstance(val, datetime | date | time):
                val = val.isoformat()
            elif isinstance(val, uuid.UUID):
                val = str(val)
            elif isinstance(val, dict | list):
                val = json.dumps(val, ensure_ascii=False)
            values.append(str(val) if val is not None else "")
        writer.writerow(values)

    return PlainTextResponse(
        output.getvalue(),
        headers={"Content-Disposition": f"attachment; filename={export_type}_export.csv"},
    )


# ═══════════════════════════════════════════════════════════
# Export logic
# ═══════════════════════════════════════════════════════════


async def export_full_data(db: AsyncSession, user, format: str = "json"):
    """Full backup: export ALL user data as a single JSON."""
    full: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": __version__,
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
        full[etype] = {"count": len(rows), "data": [model_to_dict(r) for r in rows]}

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
        raise ValueError("Full export only supports JSON format")
    return JSONResponse(full)


async def export_data_by_type(db: AsyncSession, user, export_type: str, format: str = "json", limit: int = 10000):
    """Export user data by type as JSON or CSV."""
    if export_type not in EXPORT_TYPES:
        raise ValueError(f"Unknown export type: {export_type}. Available: {list(EXPORT_TYPES)}")

    info = EXPORT_TYPES[export_type]
    model_cls = info["model"]
    # Entity uses owner_id, others use user_id
    user_col = getattr(model_cls, "user_id", None) or getattr(model_cls, "owner_id", None)

    result = await db.execute(
        select(model_cls).where(user_col == user.id).order_by(model_cls.created_at.desc()).limit(limit)
    )
    rows = result.scalars().all()

    if format == "csv":
        return rows_to_csv(rows, info["csv_headers"], export_type)
    else:
        data = [model_to_dict(r) for r in rows]
        return JSONResponse({"export_type": export_type, "count": len(data), "data": data})
