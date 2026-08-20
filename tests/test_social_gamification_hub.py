"""Tests for Platform Social Gamification Hub (Steps 88-90)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_social_pillory_board(auth_client: AsyncClient):
    """GET /social/pillory — Community Pillory Board."""
    response = await auth_client.get("/social/pillory")
    assert response.status_code == 200
    assert "Позорный Столб" in response.text


@pytest.mark.asyncio
async def test_social_verification_board(auth_client: AsyncClient):
    """GET /social/verification — Peer Review Verification Board."""
    response = await auth_client.get("/social/verification")
    assert response.status_code == 200
    assert "Народная Верификация" in response.text


@pytest.mark.asyncio
async def test_social_leaderboard(auth_client: AsyncClient):
    """GET /social/leaderboard — Anonymized Community Leaderboard."""
    response = await auth_client.get("/social/leaderboard")
    assert response.status_code == 200
    assert "Лидерборд" in response.text


@pytest.mark.asyncio
async def test_social_kudos_reaction(auth_client: AsyncClient):
    """POST /social/kudos — Send Kudos reaction to a peer."""
    response = await auth_client.post(
        "/social/kudos",
        data={
            "target_alias": "peer_test",
            "reaction": "fire",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
