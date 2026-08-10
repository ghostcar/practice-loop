"""Tests for authentication: register, login, logout, locale/theme."""

import secrets

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.user import User


def _auth_cookie_headers(user: User) -> tuple[dict, str]:
    """Auth cookie + CSRF cookie only (no X-CSRF-Token header) — simulates a native form POST.

    Returns (headers, csrf_token) so tests can reuse the token as a hidden form field.
    """
    token = create_access_token(user.id)
    csrf = secrets.token_hex(32)
    return {"Cookie": f"access_token={token}; csrf_token={csrf}"}, csrf


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


@pytest.mark.asyncio
async def test_set_theme_native_form_with_csrf_field(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession
):
    """Native form POST (theme toggle button): csrf_token form field, no header, must pass."""
    headers, csrf = _auth_cookie_headers(test_user)
    async_client.headers.update(headers)

    response = await async_client.post(
        "/settings/theme",
        data={"theme": "light", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Test fixture overrides get_db without auto-commit; persist manually.
    await db_session.commit()
    await db_session.refresh(test_user)
    assert test_user.theme == "light"


@pytest.mark.asyncio
async def test_set_locale_native_form_with_csrf_field(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession
):
    """Native form POST (locale toggle button): csrf_token form field, no header, must pass."""
    headers, csrf = _auth_cookie_headers(test_user)
    async_client.headers.update(headers)

    response = await async_client.post(
        "/settings/locale",
        data={"locale": "ru", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Test fixture overrides get_db without auto-commit; persist manually.
    await db_session.commit()
    await db_session.refresh(test_user)
    assert test_user.locale == "ru"


@pytest.mark.asyncio
async def test_set_theme_native_form_wrong_csrf_rejected(async_client: AsyncClient, test_user: User):
    """Native form POST with a mismatching csrf_token field must be rejected."""
    headers, _ = _auth_cookie_headers(test_user)
    async_client.headers.update(headers)

    response = await async_client.post(
        "/settings/theme",
        data={"theme": "light", "csrf_token": "attacker-token"},
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_csrf_meta_rendered_on_all_pages(auth_client: AsyncClient):
    """Context processor injects the CSRF token into every page, not just the dashboard."""
    cookie_header = auth_client.headers.get("Cookie", "")
    csrf = dict(p.split("=", 1) for p in cookie_header.split("; ") if "=" in p).get("csrf_token")
    assert csrf

    response = await auth_client.get("/tasks/", follow_redirects=False)
    assert response.status_code == 200
    assert f'<meta name="csrf-token" content="{csrf}">' in response.text


_PROFILE_JSON = {
    "name": "Weekend",
    "config": {
        "points": {"base": 10},
        "penalties": {"enabled": False},
        "bonuses": [],
        "thresholds": {"negative": -100, "warning": 0, "good": 100},
    },
}


@pytest.mark.asyncio
async def test_json_api_post_with_csrf_header_passes(auth_client: AsyncClient):
    """JS-fetch scenario: JSON POST with X-CSRF-Token header is accepted (points/profile)."""
    response = await auth_client.post("/api/v2/points/profiles", json=_PROFILE_JSON)
    assert response.status_code == 200
    assert response.json()["name"] == "Weekend"

    # Profile is actually persisted
    list_response = await auth_client.get("/api/v2/points/profiles")
    assert list_response.status_code == 200
    assert [p["name"] for p in list_response.json()] == ["Weekend"]


@pytest.mark.asyncio
async def test_json_api_post_without_csrf_header_rejected(async_client: AsyncClient, test_user: User):
    """JS-fetch scenario: JSON POST without the CSRF header is rejected with 403."""
    headers, _ = _auth_cookie_headers(test_user)
    async_client.headers.update(headers)

    response = await async_client.post("/api/v2/points/profiles", json=_PROFILE_JSON)
    assert response.status_code == 403
