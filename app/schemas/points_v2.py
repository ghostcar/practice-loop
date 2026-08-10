"""Pydantic schemas for the flexible points/penalties/bonuses system."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

# ── Gamification Config (stored as JSON on Entity) ──


class PointsConfig(BaseModel):
    """Points earning configuration."""

    base: int = 10
    max_per_day: int = Field(default=50, ge=0)
    profile_id: str | None = None  # UUID of a PointsProfile
    formula: str | None = None  # Custom formula string (future)


class PenaltyRedemption(BaseModel):
    """How a penalty can be redeemed through an action."""

    type: str = "clothespins"  # clothespins / bondage / self_flagellation / cold_shower / ...
    duration_min: int = 0
    count: int = 0
    description: str = ""


class PenaltyLevel(BaseModel):
    """One level of penalty for an entity."""

    level: int = 1
    deduction: int = 0  # Points deducted
    condition: str = "missed"  # missed / partial / late
    redemption: PenaltyRedemption | None = None
    auto_apply: bool = True


class PenaltyConfig(BaseModel):
    """Penalty configuration for an entity."""

    enabled: bool = True
    levels: list[PenaltyLevel] = []
    escalation: bool = False  # Whether missed penalties escalate
    escalation_step: float = 1.5  # Multiplier per escalation
    escalation_cap: int = 5  # Max escalation multiplier


class BonusCondition(BaseModel):
    """Single bonus condition."""

    code: str = ""
    condition: str = ""  # e.g. "extra_fluid_ml > 0", "level_jump == true"
    reward: int = 0
    per_unit: bool = False  # If True, reward is per unit
    description: str = ""
    enabled: bool = True


class ThresholdConfig(BaseModel):
    """Point thresholds that change behavior."""

    negative: int = -100  # Below this: severe restrictions
    warning: int = 0  # Below this: mild restrictions
    good: int = 100  # Above this: privileges


class GamificationConfig(BaseModel):
    """Full gamification config for an entity."""

    points: PointsConfig = Field(default_factory=PointsConfig)
    penalties: PenaltyConfig = Field(default_factory=PenaltyConfig)
    bonuses: list[BonusCondition] = []
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)


# ── Points Economy ──


class PointsTransactionCreate(BaseModel):
    entity_id: str | None = None
    amount: int
    transaction_type: str  # earn / spend / redeem / adjust
    reason: str = ""


class PointsTransactionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: int
    transaction_type: str
    reason: str | None
    entity_id: uuid.UUID | None
    meta: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PointsProfileCreate(BaseModel):
    name: str
    config: GamificationConfig
    is_default: bool = False


class PointsProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    config: dict
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PointsBalanceOut(BaseModel):
    points_balance: int
    xp: int
    level: int
    thresholds: ThresholdConfig | None = None
    recent_transactions: list[PointsTransactionOut] = []


# ── Schedule ──


class ScheduleRuleCreate(BaseModel):
    entity_id: uuid.UUID | None = None
    day_of_week: int = Field(ge=0, le=7)  # 7 = every day
    start_time: time
    end_time: time | None = None
    task_type: str = "mandatory"
    recurring: bool = True
    notes: str | None = None


class ScheduleRuleOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    entity_id: uuid.UUID | None
    entity_name: str | None = None
    day_of_week: int
    start_time: time
    end_time: time | None
    task_type: str
    recurring: bool
    notes: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Body Measurements ──


class BodyMeasurementCreate(BaseModel):
    measured_date: date
    time_of_day: str = "morning"
    weight: float | None = None
    chest: float | None = None
    under_chest: float | None = None
    waist: float | None = None
    hips: float | None = None
    thigh: float | None = None
    notes: str | None = None


class BodyMeasurementOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    measured_date: date
    time_of_day: str
    weight: float | None
    chest: float | None
    under_chest: float | None
    waist: float | None
    hips: float | None
    thigh: float | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BodyMeasurementChart(BaseModel):
    """Aggregated chart data for a metric."""

    metric: str
    labels: list[str]  # dates
    morning: list[float | None]
    evening: list[float | None]


# ── Inventory ──


class InventoryItemCreate(BaseModel):
    category: str
    name: str
    description: str | None = None
    quantity: int = 1
    quantity_needed: int = 1
    is_shopping_list: bool = False
    status: str = "need"
    priority: int = 0


class InventoryItemUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    description: str | None = None
    quantity: int | None = None
    quantity_needed: int | None = None
    is_shopping_list: bool | None = None
    status: str | None = None
    priority: int | None = None


class InventoryItemOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    category: str
    name: str
    description: str | None
    quantity: int
    quantity_needed: int
    is_shopping_list: bool
    status: str
    priority: int
    sort_order: int = 0
    image_path: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Import / Export ──


class ImportPayload(BaseModel):
    """Payload for data import from external services."""

    import_type: str
    # measurements / inventory / entities / activity_logs /
    # points_transactions / training_days / points_profiles
    data: list[dict[str, Any]]
    mode: str = "upsert"  # upsert / insert / replace


class ExportPayload(BaseModel):
    """Request for data export."""

    export_type: str = "all"
    # all / measurements / inventory / schedule / entities /
    # points_transactions / training_days / activity_logs
    format: str = "json"  # json / csv
    date_from: str | None = None  # ISO date
    date_to: str | None = None
    limit: int = Field(default=10000, ge=1, le=100000)
