import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# --- Entity ---


RISK_LEVELS = ("not_assessed", "low", "elevated", "high")
CONTENT_STATUSES = ("not_assessed", "draft", "reviewed", "approved", "rejected")


class EntityCreate(BaseModel):
    type: str = Field(default="one_time", pattern=r"^(one_time|series|infinite)$")
    real_name: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    short_title: str | None = Field(default=None, min_length=1, max_length=200)
    role_tags: list[str] | None = None
    task_template: dict | None = None
    tags: list[str] | None = None
    is_public: bool = False
    params_schema: dict | None = None
    risk_level: str = Field(default="not_assessed", pattern=r"^(not_assessed|low|elevated|high)$")
    penalty_enabled: bool = True
    safety_contract: dict | None = None
    automation_allowed: bool = False
    adult_only: bool = False
    content_status: str = Field(default="not_assessed", pattern=r"^(not_assessed|draft|reviewed|approved|rejected)$")
    content_version: int = Field(default=1, ge=1)


class EntityUpdate(BaseModel):
    type: str | None = Field(default=None, pattern=r"^(one_time|series|infinite)$")
    real_name: str | None = Field(default=None, min_length=1, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    short_title: str | None = Field(default=None, min_length=1, max_length=200)
    role_tags: list[str] | None = None
    task_template: dict | None = None
    tags: list[str] | None = None
    is_public: bool | None = None
    params_schema: dict | None = None
    risk_level: str | None = Field(default=None, pattern=r"^(not_assessed|low|elevated|high)$")
    penalty_enabled: bool | None = None
    safety_contract: dict | None = None
    automation_allowed: bool | None = None
    adult_only: bool | None = None
    content_status: str | None = Field(default=None, pattern=r"^(not_assessed|draft|reviewed|approved|rejected)$")
    content_version: int | None = Field(default=None, ge=1)


class EntityResponse(BaseModel):
    id: uuid.UUID
    type: str
    real_name: str
    category: str
    slug: str | None = None
    category_id: uuid.UUID | None = None
    short_title: str | None = None
    role_tags: list[str] | None = None
    task_template: dict | None = None
    tags: list[str] | None = None
    owner_id: uuid.UUID | None = None
    is_public: bool
    author_id: uuid.UUID | None = None
    params_schema: dict | None = None
    risk_level: str = "not_assessed"
    penalty_enabled: bool = True
    safety_contract: dict | None = None
    automation_allowed: bool = False
    adult_only: bool = False
    content_status: str = "not_assessed"
    content_version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# --- Opt-in ---


DESIRE_LEVELS = (
    "want_very_much",
    "want",
    "neutral",
    "reluctant",
    "strong_aversion",
)


class OptInUpdate(BaseModel):
    is_opted_in: bool = True
    rating: int | None = Field(default=None, ge=1, le=5)
    desire_level: str = Field(default="neutral", pattern=r"^(want_very_much|want|neutral|reluctant|strong_aversion)$")


class OptInResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    entity_id: uuid.UUID
    is_opted_in: bool
    rating: int | None = None
    desire_level: str
    entity_name: str | None = None

    model_config = {"from_attributes": True}
