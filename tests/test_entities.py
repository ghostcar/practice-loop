"""Tests for Entity CRUD: create, publish, delete, opt-in."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn


@pytest.mark.asyncio
async def test_create_entity(auth_client: AsyncClient, db_session: AsyncSession):
    """Create a personal entity."""
    response = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Test Activity",
            "type": "one_time",
            "category": "Test",
            "tags": "tag1, tag2",
            "is_public": False,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(Entity).where(Entity.real_name == "Test Activity"))
    entity = result.scalar_one_or_none()
    assert entity is not None
    assert entity.type == "one_time"
    assert entity.category == "Test"
    assert entity.tags == ["tag1", "tag2"]
    assert not entity.is_public


@pytest.mark.asyncio
async def test_create_public_entity(auth_client: AsyncClient, db_session: AsyncSession):
    """Create and publish a public entity."""
    response = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Public Task",
            "type": "one_time",
            "category": "Public",
            "tags": "shared",
            "is_public": True,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(Entity).where(Entity.real_name == "Public Task"))
    entity = result.scalar_one_or_none()
    assert entity is not None
    assert entity.is_public
    assert entity.author_id is not None


@pytest.mark.asyncio
async def test_publish_entity(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Publish an existing private entity."""
    entity = Entity(
        type="one_time",
        real_name="Private Task",
        category="Test",
        owner_id=test_user.id,
        is_public=False,
    )
    db_session.add(entity)
    await db_session.flush()

    response = await auth_client.post(
        f"/entities/{entity.id}/publish",
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(Entity).where(Entity.id == entity.id))
    updated = result.scalar_one()
    assert updated.is_public
    assert updated.author_id == test_user.id


@pytest.mark.asyncio
async def test_delete_entity(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Delete a personal entity."""
    entity = Entity(
        type="one_time",
        real_name="Delete Me",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    response = await auth_client.post(
        f"/entities/{entity.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(Entity).where(Entity.id == entity.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_nonexistent_entity(auth_client: AsyncClient):
    """Deleting a non-existent entity returns 404."""
    fake_id = uuid.uuid4()
    response = await auth_client.post(
        f"/entities/{fake_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_opt_in(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Opt into an entity with desire level."""
    entity = Entity(
        type="one_time",
        real_name="Opt-in Test",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    response = await auth_client.post(
        f"/entities/{entity.id}/opt-in",
        data={
            "is_opted_in": True,
            "rating": 4,
            "desire_level": "want",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == test_user.id,
            UserEntityOptIn.entity_id == entity.id,
        )
    )
    opt_in = result.scalar_one_or_none()
    assert opt_in is not None
    assert opt_in.is_opted_in
    assert opt_in.rating == 4
    assert opt_in.desire_level == "want"


@pytest.mark.asyncio
async def test_opt_in_update(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Update existing opt-in preference."""
    entity = Entity(
        type="one_time",
        real_name="Update Opt-in",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    # First opt-in
    await auth_client.post(
        f"/entities/{entity.id}/opt-in",
        data={"is_opted_in": True, "rating": 3, "desire_level": "neutral"},
        follow_redirects=False,
    )

    # Update
    response = await auth_client.post(
        f"/entities/{entity.id}/opt-in",
        data={
            "is_opted_in": False,
            "desire_level": "strong_aversion",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == test_user.id,
            UserEntityOptIn.entity_id == entity.id,
        )
    )
    opt_in = result.scalar_one_or_none()
    assert opt_in is not None
    assert not opt_in.is_opted_in
    assert opt_in.desire_level == "strong_aversion"
