"""Medication service layer — public API re-export.

Split from monolithic med_service.py (3107 lines → 12 focused modules).
All public symbols are re-exported here for backward compatibility.

Modules:
  schemas      — Pydantic DTO
  regimen      — meal timing, schedule times, free-text parser
  substances   — substance normalization, component sync
  units        — unit conversion, daily limits, equivalents
  serializers  — model → dict
  graph        — selectinload graph loading, lookups
  course       — course CRUD
  schedule_stock_kit — schedule / stock / kit CRUD
  intake       — intake recording
  analogs      — analog search (LLM + directory)
  page_context — page context builder + today summary
  crud         — medication CRUD + JSON API
"""

from __future__ import annotations

# ── Analogs ──────────────────────────────────────────────────────────────────
from app.services.med.analogs import (
    autofill_info,
    find_analogs,
    get_equivalents,
)

# ── Course ───────────────────────────────────────────────────────────────────
from app.services.med.course import (
    add_course_item,
    batch_combine_course_slots,
    course_summary,
    create_course,
    delete_course,
    delete_course_item,
    get_course,
    set_course_status,
    update_course,
)

# ── CRUD ─────────────────────────────────────────────────────────────────────
from app.services.med.crud import (
    create_medication,
    delete_medication,
    get_csv_export,
    get_json_export,
    json_create_kit,
    json_create_medication,
    json_create_schedule,
    json_create_stock,
    json_delete_kit,
    json_delete_medication,
    json_delete_schedule,
    json_delete_stock,
    json_list_kits,
    json_list_medications,
    json_list_schedules,
    json_list_stocks,
    json_update_medication,
    maybe_schedule_from_instructions,
    migrate_inventory,
    update_medication,
)

# ── Graph ────────────────────────────────────────────────────────────────────
from app.services.med.graph import (
    get_kit,
    get_med,
    get_schedule,
    get_stock,
    load_meds_graph,
    med_matches_query,
)

# ── Intake ───────────────────────────────────────────────────────────────────
from app.services.med.intake import (
    delete_intake,
    record_batch_intake,
    record_intake,
    record_prn_intake,
)

# ── Page context ─────────────────────────────────────────────────────────────
from app.services.med.page_context import (
    get_med_page_context,
    schedule_summary,
)

# ── Regimen ──────────────────────────────────────────────────────────────────
from app.services.med.regimen import (
    EXPIRING_SOON_DAYS,
    MEAL_OFFSETS,
    MEAL_TIMES,
    REGIMEN_PRESETS,
    course_days,
    doses_today,
    intake_slots_for_schedule,
    intakes_per_day,
    parse_regimen_text,
    regimen_to_text,
    schedule_times,
)

# ── Schedule / Stock / Kit ───────────────────────────────────────────────────
from app.services.med.schedule_stock_kit import (
    add_stock_to_kit,
    create_kit,
    create_schedule,
    create_stock,
    delete_kit,
    delete_schedule,
    delete_stock,
    find_medication_by_barcode,
    update_kit,
    update_schedule,
    update_stock,
)

# ── Schemas ──────────────────────────────────────────────────────────────────
from app.services.med.schemas import (
    AutofillBody,
    ComponentItem,
    CourseBody,
    CourseItemBody,
    IntakeBody,
    KitBody,
    MedicationBody,
    RegimenParseBody,
    ScheduleBody,
    StockBody,
)

# ── Serializers ──────────────────────────────────────────────────────────────
from app.services.med.serializers import (
    composition_label,
    composition_rows,
    med_dict,
    schedule_dict,
    stock_dict,
)

# ── Substances ───────────────────────────────────────────────────────────────
from app.services.med.substances import (
    extract_med_substances,
    find_or_create_substance,
    get_substances,
    normalize_substance,
    parse_components_payload,
    sync_med_components,
)

# ── Units ────────────────────────────────────────────────────────────────────
from app.services.med.units import (
    ME_TO_MCG,
    UNIT_TO_MG,
    daily_limit_exceedances,
    day_components,
    equivalent_candidates,
    kit_location_label,
    location_path,
    med_substance_keys,
    med_substance_mg_map,
    to_mg,
    variant_for_day,
)

# ── Wizard & Interactions ───────────────────────────────────────────────────
from app.services.med.wizard import (
    PRESET_PROTOCOLS,
    apply_generated_course,
    check_drug_interactions,
    generate_course_protocol,
)

__all__ = [
    # schemas
    "AutofillBody", "ComponentItem", "CourseBody", "CourseItemBody",
    "IntakeBody", "KitBody", "MedicationBody", "RegimenParseBody",
    "ScheduleBody", "StockBody",
    # regimen
    "EXPIRING_SOON_DAYS", "MEAL_OFFSETS", "MEAL_TIMES", "REGIMEN_PRESETS", "course_days",
    "doses_today", "intake_slots_for_schedule", "intakes_per_day",
    "parse_regimen_text", "regimen_to_text", "schedule_times",
    # substances
    "extract_med_substances", "find_or_create_substance", "get_substances", "normalize_substance",
    "parse_components_payload", "sync_med_components",
    # units
    "ME_TO_MCG", "UNIT_TO_MG", "daily_limit_exceedances",
    "equivalent_candidates", "kit_location_label", "location_path",
    "med_substance_keys", "med_substance_mg_map", "to_mg",
    "variant_for_day", "day_components",
    # serializers
    "composition_label", "composition_rows", "med_dict", "schedule_dict", "stock_dict",
    # graph
    "get_kit", "get_med", "get_schedule", "get_stock",
    "load_meds_graph", "med_matches_query",
    # course
    "add_course_item", "batch_combine_course_slots", "course_summary", "create_course", "delete_course",
    "delete_course_item", "get_course", "set_course_status", "update_course",
    # schedule_stock_kit
    "add_stock_to_kit", "create_kit", "create_schedule", "create_stock",
    "delete_kit", "delete_schedule", "delete_stock",
    "find_medication_by_barcode", "update_kit", "update_schedule", "update_stock",
    # intake
    "delete_intake", "record_batch_intake", "record_intake", "record_prn_intake",
    # analogs
    "autofill_info", "find_analogs", "get_equivalents",
    # page_context
    "get_med_page_context", "schedule_summary",
    # wizard
    "PRESET_PROTOCOLS", "apply_generated_course", "check_drug_interactions", "generate_course_protocol",
    # crud
    "create_medication", "delete_medication", "get_csv_export",
    "get_json_export", "json_create_kit", "json_create_medication",
    "json_create_schedule", "json_create_stock", "json_delete_kit",
    "json_delete_medication", "json_delete_schedule", "json_delete_stock",
    "json_list_kits", "json_list_medications", "json_list_schedules",
    "json_list_stocks", "json_update_medication",
    "maybe_schedule_from_instructions", "migrate_inventory", "update_medication",
]
