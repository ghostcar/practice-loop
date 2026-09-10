"""Personal Care service — public API re-export.

Split from monolithic care_service.py (1162 lines → 9 focused modules).
All public symbols are re-exported here for backward compatibility.
"""

from __future__ import annotations

# ── Schemas ──────────────────────────────────────────────────────────────────
from app.services.care.schemas import CourseBody, EntryBody, ProductBody, RoutineBody

# ── Helpers ──────────────────────────────────────────────────────────────────
from app.services.care.helpers import (
    _now_utc,
    parse_date,
    parse_int,
    parse_scale,
    resolve_catalog_item,
    resolve_inventory_item,
    resolve_products,
    validate_routine,
)

# ── Relations ────────────────────────────────────────────────────────────────
from app.services.care.relations import cycle_snapshot, set_entry_products, set_routine_products

# ── Summary ──────────────────────────────────────────────────────────────────
from app.services.care.summary import (
    entry_product_map,
    get_care_summary,
    inventory_options,
    media_map,
)

# ── Serializers ──────────────────────────────────────────────────────────────
from app.services.care.serializers import (
    course_json,
    entry_json,
    entry_view,
    product_json,
    product_view,
    routine_json,
)

# ── Page context ─────────────────────────────────────────────────────────────
from app.services.care.page_context import get_care_page_context

# ── CRUD ─────────────────────────────────────────────────────────────────────
from app.services.care.crud import (
    attach_entry_media,
    attach_product_media,
    create_course,
    create_entry,
    create_product,
    create_routine,
    delete_course,
    delete_entry,
    delete_product,
    delete_routine,
    mark_course_session_done,
    mark_course_session_skipped,
)

# ── JSON API ─────────────────────────────────────────────────────────────────
from app.services.care.json_api import (
    json_care_summary,
    json_create_course,
    json_create_entry,
    json_create_product,
    json_create_routine,
    json_delete_course,
    json_delete_entry,
    json_delete_product,
    json_delete_routine,
    json_list_courses,
    json_list_products,
)

__all__ = [
    "CourseBody", "EntryBody", "ProductBody", "RoutineBody",
    "_now_utc", "parse_date", "parse_int", "parse_scale",
    "resolve_catalog_item", "resolve_inventory_item", "resolve_products", "validate_routine",
    "cycle_snapshot", "set_entry_products", "set_routine_products",
    "get_care_summary", "media_map", "entry_product_map", "inventory_options",
    "product_view", "entry_view", "routine_json", "product_json", "entry_json", "course_json",
    "get_care_page_context",
    "create_routine", "delete_routine", "create_product", "delete_product",
    "create_entry", "delete_entry", "attach_entry_media", "attach_product_media",
    "create_course", "delete_course", "mark_course_session_done", "mark_course_session_skipped",
    "json_care_summary", "json_list_products", "json_list_courses",
    "json_create_routine", "json_create_entry", "json_create_product", "json_create_course",
    "json_delete_routine", "json_delete_entry", "json_delete_product", "json_delete_course",
]
