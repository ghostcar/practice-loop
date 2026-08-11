"""Pydantic schemas for reference data: BodyPart, TaskLocation, InventoryCategory,
and task-level links (TaskBodyTarget, TaskLocationUsage, TaskInventoryUsage).

update2.md — normalised references API layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── BodyPart ────────────────────────────────────────────────────────────


class BodyPartOut(BaseModel):
    id: uuid.UUID
    slug: str
    title_ru: str
    title_en: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    body_system: str = "general"
    is_sensitive: bool = False
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class BodyPartTreeNode(BaseModel):
    """Recursive tree node for hierarchical body part display."""

    id: uuid.UUID
    slug: str
    title_ru: str
    title_en: str | None = None
    body_system: str = "general"
    is_sensitive: bool = False
    is_active: bool = True
    sort_order: int = 0
    children: list[BodyPartTreeNode] = []


# ── TaskBodyTarget ──────────────────────────────────────────────────────


class TaskBodyTargetCreate(BaseModel):
    body_part_id: uuid.UUID | None = None
    target_role: str = "primary_target"
    side: str = "both"
    planned_intensity: int | None = Field(default=None, ge=1, le=5)
    actual_intensity: int | None = Field(default=None, ge=1, le=5)
    planned_duration_seconds: int | None = None
    actual_duration_seconds: int | None = None
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None


class TaskBodyTargetBatch(BaseModel):
    """Replace all body targets for a task atomically."""

    targets: list[TaskBodyTargetCreate] = []


class TaskBodyTargetOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    body_part_id: uuid.UUID | None = None
    body_part_name_snapshot: str
    target_role: str
    side: str
    planned_intensity: int | None = None
    actual_intensity: int | None = None
    planned_duration_seconds: int | None = None
    actual_duration_seconds: int | None = None
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── TaskLocation ────────────────────────────────────────────────────────


class TaskLocationOut(BaseModel):
    id: uuid.UUID
    slug: str
    title_ru: str
    title_en: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    location_type: str = "other"
    privacy_level: str = "private"
    is_active: bool = True
    is_custom: bool = False
    owner_id: uuid.UUID | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskLocationTreeNode(BaseModel):
    id: uuid.UUID
    slug: str
    title_ru: str
    title_en: str | None = None
    location_type: str = "other"
    privacy_level: str = "private"
    is_active: bool = True
    is_custom: bool = False
    owner_id: uuid.UUID | None = None
    sort_order: int = 0
    children: list[TaskLocationTreeNode] = []


class TaskLocationCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    title_ru: str = Field(min_length=1, max_length=200)
    title_en: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    location_type: str = "other"
    privacy_level: str = "private"
    sort_order: int = 0


class TaskLocationUpdate(BaseModel):
    title_ru: str | None = None
    title_en: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    location_type: str | None = None
    privacy_level: str | None = None
    sort_order: int | None = None


# ── TaskLocationUsage ───────────────────────────────────────────────────


class TaskLocationUsageCreate(BaseModel):
    location_id: uuid.UUID | None = None
    location_role: str = "primary_location"
    is_required: bool = False
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None


class TaskLocationUsageBatch(BaseModel):
    usages: list[TaskLocationUsageCreate] = []


class TaskLocationUsageOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    location_id: uuid.UUID | None = None
    location_name_snapshot: str
    location_role: str
    is_required: bool = False
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── InventoryCategory ───────────────────────────────────────────────────


class InventoryCategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


# ── TaskInventoryUsage ──────────────────────────────────────────────────


class TaskInventoryUsageCreate(BaseModel):
    inventory_item_id: uuid.UUID | None = None
    usage_role: str = "primary_tool"
    planned_quantity: float | None = Field(default=None, ge=0)
    actual_quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None
    is_required: bool = False
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None


class TaskInventoryUsageBatch(BaseModel):
    usages: list[TaskInventoryUsageCreate] = []


class TaskInventoryUsageOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    inventory_item_id: uuid.UUID | None = None
    inventory_name_snapshot: str
    inventory_category_snapshot: str | None = None
    usage_role: str
    planned_quantity: float | None = None
    actual_quantity: float | None = None
    unit: str | None = None
    is_required: bool = False
    sort_order: int = 0
    planned_notes: str | None = None
    actual_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
