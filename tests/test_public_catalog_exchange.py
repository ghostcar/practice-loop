"""Tests for Public Catalog & Community Template Exchange (Step 78)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import ActivityCatalogItem
from app.models.user import User


@pytest.mark.asyncio
async def test_public_catalog_page(auth_client: AsyncClient):
    """GET /catalog/public — Public Catalog Page."""
    response = await auth_client.get("/catalog/public")
    assert response.status_code == 200
    assert "Публичный Каталог Задач" in response.text


@pytest.mark.asyncio
async def test_cannot_import_another_users_private_catalog_item(
    auth_client: AsyncClient, db_session: AsyncSession, _test_password_hash: str
):
    owner = User(email="catalog-owner@example.com", password_hash=_test_password_hash)
    db_session.add(owner)
    await db_session.flush()
    private_item = ActivityCatalogItem(name="Private", owner_id=owner.id, is_public=False)
    db_session.add(private_item)
    await db_session.flush()

    response = await auth_client.post(
        "/catalog/import-template",
        data={"item_id": str(private_item.id)},
        follow_redirects=False,
    )
    assert response.status_code == 404
