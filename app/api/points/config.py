"""Gamification config endpoints — get/update entity gamification settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.entity import Entity
from app.models.user import User
from app.schemas.points_v2 import GamificationConfig
from app.security import require_entity_owner

router = APIRouter(tags=["v2"])


@router.get("/entities/{entity_id}/gamification")
async def get_gamification_config(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get gamification config for an entity (public or owned)."""
    result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")
    return {
        "entity_id": str(entity.id),
        "gamification_config": entity.gamification_config or {},
    }


@router.put("/entities/{entity_id}/gamification")
async def update_gamification_config(
    entity_id: uuid.UUID,
    config: GamificationConfig,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update gamification config for an entity (owner only)."""
    entity = await require_entity_owner(entity_id, user, db)
    entity.gamification_config = config.model_dump()
    db.add(entity)
    return {"status": "ok"}
