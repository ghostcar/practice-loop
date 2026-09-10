"""Pydantic DTO used by JSON API endpoints."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class ComponentItem(BaseModel):
    substance: str | None = None
    name: str | None = None  # алиас substance
    inn: str | None = None
    amount: float | None = None
    unit: str | None = None
    variant: str | None = None
    daily_max_amt: float | None = None
    daily_max_unit: str | None = None
    daily_max_note: str | None = None

    def row(self) -> dict:
        return {
            "substance": (self.substance or self.name or "").strip(),
            "inn": (self.inn or "").strip() or None,
            "amount": self.amount,
            "unit": (self.unit or "").strip() or None,
            "variant": (self.variant or "").strip() or None,
            "daily_max_amt": self.daily_max_amt,
            "daily_max_unit": self.daily_max_unit,
            "daily_max_note": self.daily_max_note,
        }


class MedicationBody(BaseModel):
    name: str
    kind: str = "medication"
    active_ingredient: str | None = None
    form: str | None = None
    strength: str | None = None
    unit: str | None = None
    instructions: str | None = None
    notes: str | None = None
    allow_ul_override: bool = False
    components: list[ComponentItem] | None = None
    is_active: bool = True


class StockBody(BaseModel):
    medication_id: uuid.UUID
    quantity: float = 0.0
    unit: str | None = None
    kit_id: uuid.UUID | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    low_stock_threshold: float | None = None
    notes: str | None = None


class ScheduleBody(BaseModel):
    medication_id: uuid.UUID
    dose_quantity: float = 1.0
    dose_unit: str | None = None
    frequency_type: str = "daily"
    times_per_day: int | None = None
    times_of_day: list[str] | None = None
    interval_hours: float | None = None
    days_of_week: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    food_relation: str | None = None
    duration_days: int | None = None
    meal_timing: dict | None = None
    meal_offset_min: int | None = None
    instructions: str | None = None
    is_active: bool = True


class KitBody(BaseModel):
    name: str
    location: str | None = None
    location_id: uuid.UUID | None = None
    notes: str | None = None


class IntakeBody(BaseModel):
    schedule_id: uuid.UUID | None = None
    status: str = "taken"
    taken_at: str | None = None
    quantity_taken: float | None = None
    notes: str | None = None
    substituted_for_id: uuid.UUID | None = None
    ul_confirmed: bool = False
    kit_id: uuid.UUID | None = None


class CourseItemBody(BaseModel):
    medication_id: uuid.UUID
    dose_quantity: float = 1.0
    dose_unit: str | None = None
    frequency_type: str = "daily"
    times_per_day: int | None = None
    times_of_day: list[str] | None = None
    interval_hours: float | None = None
    days_of_week: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    food_relation: str | None = None
    duration_days: int | None = None
    meal_timing: dict | None = None
    meal_offset_min: int | None = None
    instructions: str | None = None


class CourseBody(BaseModel):
    name: str
    notes: str | None = None
    start_date: date | None = None
    items: list[CourseItemBody] = []


class RegimenParseBody(BaseModel):
    text: str


class AutofillBody(BaseModel):
    name: str
