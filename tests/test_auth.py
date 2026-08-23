"""Tests for authentication: register, login, logout, locale/theme."""

import secrets

import pytest
from httpx import AsyncClient
from sqlalchemy import select
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
    """Logout clears cookie and redirects. POST only (audit: GET logout is a vector)."""
    # GET is rejected (no CSRF on GET; logout must be a POST action)
    response = await async_client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 405

    # POST clears both cookies and redirects
    response = await async_client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "csrf_token=" in set_cookie


@pytest.mark.asyncio
async def test_dashboard_requires_auth(async_client: AsyncClient):
    """Dashboard without auth returns 401."""
    response = await async_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authed_user_redirected_from_register_page(async_client: AsyncClient, test_user):
    """GET /register while authenticated redirects to /dashboard.

    The register form carries no csrf_token and CSRF is enforced for authed
    sessions, so a second registration would 403 — redirect instead (ADR-148).
    """
    headers, _ = _auth_cookie_headers(test_user)
    resp = await async_client.get("/register", headers=headers, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


@pytest.mark.asyncio
async def test_authed_user_redirected_from_login_page(async_client: AsyncClient, test_user):
    """GET /login while authenticated redirects to /dashboard."""
    headers, _ = _auth_cookie_headers(test_user)
    resp = await async_client.get("/login", headers=headers, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


@pytest.mark.asyncio
async def test_authed_register_post_redirects_no_account(
    async_client: AsyncClient, db_session: AsyncSession, test_user
):
    """POST /auth/register while authenticated must not create a second account."""
    headers, csrf = _auth_cookie_headers(test_user)
    resp = await async_client.post(
        "/auth/register",
        headers=headers,
        data={"email": "dupe@example.com", "password": "pass1234", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    result = await db_session.execute(select(User).where(User.email == "dupe@example.com"))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_authed_login_post_redirects(async_client: AsyncClient, test_user):
    """POST /auth/login while authenticated redirects to /dashboard (no re-auth)."""
    headers, csrf = _auth_cookie_headers(test_user)
    resp = await async_client.post(
        "/auth/login",
        headers=headers,
        data={"email": "nobody@example.com", "password": "pass1234", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


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


# --- Import page (S53): /import reachable from nav + template/upload UI ---


@pytest.mark.asyncio
async def test_import_page_renders_with_nav_link(auth_client: AsyncClient):
    """Import page is reachable and the navbar links to it."""
    response = await auth_client.get("/import", follow_redirects=False)
    assert response.status_code == 200

    # Nav link present on the page itself (active state)
    assert 'href="/import"' in response.text
    assert 'aria-current="page"' in response.text

    # Template cards + upload UI render
    assert "/import/template/" in response.text
    assert "drop-zone" in response.text
    assert "upload-result" in response.text


@pytest.mark.asyncio
async def test_import_page_has_download_links(auth_client: AsyncClient):
    """Every template type offers CSV + JSON download links."""
    response = await auth_client.get("/import", follow_redirects=False)
    assert response.status_code == 200

    for fmt in ("csv", "json"):
        assert f"?format={fmt}" in response.text

    # The API template endpoint itself serves a downloadable CSV
    tpl = await auth_client.get("/import/template/entities?format=csv")
    assert tpl.status_code == 200
    assert "Content-Disposition" in tpl.headers
    assert "type,real_name" in tpl.text


# --- Regression (S51): every native POST form must carry a hidden csrf_token ---


def test_all_native_post_forms_have_csrf_hidden_field():
    """Static check: every `<form ... method="post">` in authenticated templates
    must include `<input ... name="csrf_token">`. Missed forms (admin seed,
    sessions, my_entities, llm_configs, privacy, notifications, achievements)
    silently returned 403 on a fresh deploy.

    login/register are exempt: unauthenticated requests skip CSRF verification.
    """
    import re
    from pathlib import Path

    templates_dir = Path(__file__).resolve().parent.parent / "app" / "templates"
    exempt = {"login.html", "register.html"}
    form_re = re.compile(r"<form[^>]*method=['\"]post['\"]")
    hidden_re = re.compile(r"name=['\"]csrf_token['\"]")

    missing: list[str] = []
    for path in sorted(templates_dir.glob("*.html")):
        if path.name in exempt:
            continue
        content = path.read_text(encoding="utf-8")
        forms = list(form_re.finditer(content))
        for form in forms:
            # The hidden input must appear inside this <form>...</form> block.
            # Valid HTML forbids nested forms, so slicing to the first
            # </form> is unambiguous.
            closing = content.find("</form>", form.end())
            if closing == -1:
                raise AssertionError(f"{path.name}: unclosed <form> tag")
            form_body = content[form.end() : closing]
            if not hidden_re.search(form_body):
                missing.append(f"{path.name}: {form.group(0)[:60]}...")

    assert not missing, "POST forms without csrf_token hidden field:\n" + "\n".join(missing)
