"""Tests for Partner Co-Op Session Portal (Steps 75 & 77)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_partner_coop_session_page(auth_client: AsyncClient):
    """GET /sessions/coop — Partner Co-Op Session Portal."""
    response = await auth_client.get("/sessions/coop")
    assert response.status_code == 200
    assert "Партнерская Совместная Сессия" in response.text
