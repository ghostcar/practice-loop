"""Tests for authentication: register, login, logout, locale/theme."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    """Register a new user and get redirected to login."""
    response = await async_client.post(
        "/auth/register",
        data={"email": "new@example.com", "password": "pass1234"},
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_register_short_password(async_client: AsyncClient):
    """Password < 6 chars should fail validation."""
    response = await async_client.post(
        "/auth/register",
        data={"email": "short@example.com", "password": "12"},
        follow_redirects=False,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    """Registered user can log in."""
    await async_client.post(
        "/auth/register",
        data={"email": "logme@example.com", "password": "secret123"},
        follow_redirects=False,
    )
    response = await async_client.post(
        "/auth/login",
        data={"email": "logme@example.com", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient):
    """Logout clears cookie and redirects."""
    response = await async_client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in cookie


@pytest.mark.asyncio
async def test_dashboard_requires_auth(async_client: AsyncClient):
    """Dashboard without auth returns 401."""
    response = await async_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_set_locale(auth_client: AsyncClient):
    """Change locale preference."""
    response = await auth_client.post(
        "/settings/locale",
        data={"locale": "ru"},
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_set_theme(auth_client: AsyncClient):
    """Change theme preference."""
    response = await auth_client.post(
        "/settings/theme",
        data={"theme": "light"},
        follow_redirects=False,
    )
    assert response.status_code == 303
