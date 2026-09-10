"""Sexual Journal — Pydantic DTOs."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class EntryBody(BaseModel):
    entry_date: date
    partner_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    activity_log_id: uuid.UUID | None = None
    care_product_ids: list[uuid.UUID] | None = None


class CompleteBody(BaseModel):
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    care_product_ids: list[uuid.UUID] | None = None


class PartnerBody(BaseModel):
    name: str
    notes: str | None = None
