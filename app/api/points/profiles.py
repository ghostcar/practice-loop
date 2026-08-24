"""Points profiles — CRUD + assign to entity."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.points import PointsProfile
from app.models.user import User
from app.schemas.points_v2 import PointsProfileCreate, PointsProfileOut
from app.security import require_entity_owner

router = APIRouter(tags=["v2"])


@router.get("/points/profiles", response_model=list[PointsProfileOut])
async def list_points_profiles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(PointsProfile).where(PointsProfile.user_id == user.id))
    return [PointsProfileOut.model_validate(p) for p in result.scalars().all()]


@router.post("/points/profiles", response_model=PointsProfileOut)
async def create_points_profile(
    data: PointsProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = PointsProfile(
        user_id=user.id,
        name=data.name,
        config=data.config.model_dump(),
        is_default=data.is_default,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return PointsProfileOut.model_validate(profile)


@router.delete("/points/profiles/{profile_id}")
async def delete_points_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PointsProfile).where(PointsProfile.id == profile_id, PointsProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")
    await db.delete(profile)
    return {"status": "deleted"}


@router.post("/entities/{entity_id}/assign-profile")
async def assign_profile_to_entity(
    entity_id: uuid.UUID,
    profile_id: uuid.UUID = Query(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Assign a PointsProfile to an entity (owner only)."""
    entity = await require_entity_owner(entity_id, user, db)

    profile_result = await db.execute(
        select(PointsProfile).where(PointsProfile.id == profile_id, PointsProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")

    # Copy profile config to entity
    entity.gamification_config = profile.config
    if entity.gamification_config and isinstance(entity.gamification_config, dict):
        entity.gamification_config["points"]["profile_id"] = str(profile_id)
    db.add(entity)
    return {"status": "assigned", "profile_name": profile.name}
