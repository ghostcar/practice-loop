"""Tests for Public Catalog & Community Template Exchange (Step 78)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_public_catalog_page(auth_client: AsyncClient):
    """GET /catalog/public — Public Catalog Page."""
    response = await auth_client.get("/catalog/public")
    assert response.status_code == 200
    assert "Публичный Каталог Задач" in response.text
