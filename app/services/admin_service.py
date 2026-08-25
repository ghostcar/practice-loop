"""Admin Service — business logic extracted from app.api.admin.

Covers: user management (role/disable/password), seeding, AI generator,
prompt library management, schema builder context.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models.api_token import ApiToken
from app.models.user import User

USER_ROLES = ("user", "moderator", "admin")


async def get_user_list_context(db: AsyncSession) -> dict:
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return {"users": users, "roles": USER_ROLES}


async def _managed_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise ValueError("User not found")
    return target


async def set_user_role(
    db: AsyncSession, user_id: uuid.UUID, role: str, admin_id: uuid.UUID,
) -> None:
    if role not in USER_ROLES:
        raise ValueError("Invalid role")
    target = await _managed_user(db, user_id)
    if target.id == admin_id and role != "admin":
        raise ValueError("An administrator cannot demote their own account")
    target.role = role
    db.add(target)
    await db.flush()


async def set_user_disabled(
    db: AsyncSession, user_id: uuid.UUID, disabled: bool, admin_id: uuid.UUID,
) -> None:
    target = await _managed_user(db, user_id)
    if target.id == admin_id and disabled:
        raise ValueError("An administrator cannot disable their own account")
    target.disabled_at = datetime.now(UTC) if disabled else None
    db.add(target)
    if disabled:
        await db.execute(delete(ApiToken).where(ApiToken.user_id == target.id))
    await db.flush()


async def reset_user_password(
    db: AsyncSession, user_id: uuid.UUID, new_password: str,
    confirm_password: str, admin_id: uuid.UUID,
) -> None:
    target = await _managed_user(db, user_id)
    if target.id == admin_id:
        raise ValueError("Use account settings to change your own password")
    if not 6 <= len(new_password) <= 128:
        raise ValueError("Password must contain 6-128 characters")
    if new_password != confirm_password:
        raise ValueError("Passwords do not match")
    target.password_hash = hash_password(new_password)
    db.add(target)
    await db.execute(delete(ApiToken).where(ApiToken.user_id == target.id))
    await db.flush()


async def get_schema_builder_context(db: AsyncSession) -> dict:
    from app.models.entity import Entity
    entities = (await db.execute(select(Entity))).scalars().all()
    return {"entities": entities}


async def get_catalog_editor_context(db: AsyncSession) -> dict:
    from app.models.entity import Entity
    entities = (await db.execute(select(Entity).order_by(Entity.created_at.desc()))).scalars().all()
    return {"items": entities}


async def execute_ai_generator(
    db: AsyncSession, admin_id: uuid.UUID,
    *, mode: str = "expanded", explicit_level: int = 4,
    remove_filters: bool = False, custom_directives: str = "",
) -> list:
    import logging

    from app.llm.pipeline import get_active_llm_config
    from app.llm.pipeline.content_generator import (
        build_catalog_generation_prompt,
        generate_catalog_proposals,
    )

    logger = logging.getLogger(__name__)
    llm_config = await get_active_llm_config(db, admin_id)
    if not llm_config:
        return []
    sys_prompt, usr_prompt = build_catalog_generation_prompt(
        mode=mode, explicit_level=explicit_level,
        custom_directives=custom_directives, remove_filters=remove_filters,
    )
    try:
        return await generate_catalog_proposals(
            db=db, user_id=admin_id, llm_config=llm_config,
            system_prompt=sys_prompt, user_prompt=usr_prompt,
        )
    except Exception as e:
        logger.error(f"AI Catalog Generation failed: {e}")
        return []


async def get_prompts_hub_context(db: AsyncSession) -> dict:
    from app.models.prompt_library import PromptLibraryItem
    from app.prompt_library import seed_prompt_library

    await seed_prompt_library(db)
    items = (await db.execute(
        select(PromptLibraryItem).order_by(PromptLibraryItem.key)
    )).scalars().all()
    system_prompts = [i for i in items if i.library_type == "system"]
    user_prompts = [i for i in items if i.library_type == "user"]
    return {"system_prompts": system_prompts, "user_prompts": user_prompts}


async def update_prompt_item(db: AsyncSession, prompt_id: uuid.UUID, content: str) -> None:
    from app.models.prompt_library import PromptLibraryItem

    item = (await db.execute(
        select(PromptLibraryItem).where(PromptLibraryItem.id == prompt_id)
    )).scalar_one_or_none()
    if not item:
        raise ValueError("Prompt item not found")
    item.template_content = content
    item.is_customized = True
    item.updated_at = datetime.now(UTC)
    await db.flush()


async def reset_prompt_item(db: AsyncSession, prompt_id: uuid.UUID) -> None:
    from app.models.prompt_library import PromptLibraryItem
    from app.prompt_library import DEFAULT_PROMPT_REGISTRY

    item = (await db.execute(
        select(PromptLibraryItem).where(PromptLibraryItem.id == prompt_id)
    )).scalar_one_or_none()
    if not item:
        raise ValueError("Prompt item not found")
    for reg in DEFAULT_PROMPT_REGISTRY:
        if reg["key"] == item.key:
            item.template_content = reg["template_content"]
            item.is_customized = False
            item.updated_at = datetime.now(UTC)
            await db.flush()
            break
