import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LLMConfigCreate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=100)
    api_base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = None
    model_name: str = Field(min_length=1, max_length=200)
    is_active: bool = False
    llm_mode: str = Field(default="full", pattern="^(full|abstract)$")
    store_raw_response: bool = Field(
        default=True,
        description="REM §7.5: if False, LLM raw payloads are NOT persisted to ActivityLog. "
        "Usage metrics are still kept.",
    )


class LLMConfigUpdate(BaseModel):
    provider_name: str | None = Field(default=None, min_length=1, max_length=100)
    api_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    llm_mode: str | None = Field(default=None, pattern="^(full|abstract)$")
    store_raw_response: bool | None = None


class LLMConfigResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider_name: str
    api_base_url: str
    api_key_masked: str  # e.g. "sk-...****"
    model_name: str
    is_active: bool
    llm_mode: str
    store_raw_response: bool
    total_tokens: int
    total_cost: float
    created_at: datetime

    model_config = {"from_attributes": True}
