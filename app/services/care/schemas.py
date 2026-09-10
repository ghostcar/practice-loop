"""Personal Care — Pydantic DTOs."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class RoutineBody(BaseModel):
    name: str
    catalog_item_id: uuid.UUID | None = None
    area: str = "other"
    kind: str = "home"
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    frequency_days: int | None = Field(default=None, ge=1, le=3650)
    notes: str | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class EntryBody(BaseModel):
    entry_date: date
    routine_id: uuid.UUID | None = None
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    skin_reaction: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class ProductBody(BaseModel):
    name: str
    category: str = "other"
    brand: str | None = None
    notes: str | None = None
    inventory_item_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    quantity: int = Field(default=0, ge=0, le=100000)
    expiry_date: date | None = None


class CourseBody(BaseModel):
    name: str
    area: str = "other"
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    total_sessions: int = Field(default=1, ge=1, le=200)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    start_date: date | None = None
    notes: str | None = None
    catalog_item_id: uuid.UUID | None = None
