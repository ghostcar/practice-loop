"""Pydantic schemas for calendar availability system."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import time as time_type
from typing import Any

from pydantic import BaseModel, Field


class AvailabilityWindowCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=7)  # 7 = every day
    start_time: time_type
    end_time: time_type
    label: str = "free"
    policy: str = "allowed"  # allowed / disallowed / passive_only


class AvailabilityWindowOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    day_of_week: int
    start_time: time_type
    end_time: time_type
    label: str
    policy: str

    model_config = {"from_attributes": True}


class CalendarTemplateCreate(BaseModel):
    name: str
    is_default: bool = False
    windows: list[AvailabilityWindowCreate] = []


class CalendarTemplateOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    is_default: bool
    windows: list[AvailabilityWindowOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class CalendarOverrideCreate(BaseModel):
    template_id: uuid.UUID
    start_date: date
    end_date: date
    label: str | None = None


class CalendarOverrideOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str | None = None
    start_date: date
    end_date: date
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AvailabilityCheckRequest(BaseModel):
    target_time: datetime
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    intensity: str = "active"  # active / passive / neutral


class AvailabilityCheckResponse(BaseModel):
    available: bool
    policy: str | None = None  # allowed / disallowed / passive_only
    window_label: str | None = None
    template_name: str | None = None
    reason: str | None = None


class DaySchedule(BaseModel):
    """Resolved schedule for a single day — used in LLM prompts."""
    date: date
    template_name: str
    windows: list[dict[str, Any]]  # [{start, end, label, policy}]


class EntityIntensityUpdate(BaseModel):
    intensity: str = "active"  # active / passive / neutral
