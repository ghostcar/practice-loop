"""Tests for Categorized User Prompt Library Viewer (Step 72)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_prompt_library_page(auth_client: AsyncClient):
    """GET /prompts/library — Prompt Library Viewer."""
    response = await auth_client.get("/prompts/library")
    assert response.status_code == 200
    assert "Библиотека ИИ-Промптов" in response.text
