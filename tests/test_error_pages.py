"""Tests for error pages: HTML for browsers, JSON for API clients."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_404_returns_html_for_browser(auth_client: AsyncClient):
    """A browser request (Accept: text/html) to a missing page gets an HTML error page."""
    response = await auth_client.get("/this-page-does-not-exist", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "error.html" not in response.text  # rendered template, not a redirect
    assert "404" in response.text


@pytest.mark.asyncio
async def test_404_returns_json_for_api(auth_client: AsyncClient):
    """An API path missing route returns JSON, not HTML."""
    response = await auth_client.get("/api/v2/does-not-exist", headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_entity_404_html_for_browser(auth_client: AsyncClient):
    """A form POST raising HTTPException(404) renders HTML for browsers."""
    response = await auth_client.post(
        f"/entities/{uuid.uuid4()}/delete",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_entity_404_json_for_api_client(auth_client: AsyncClient):
    """The same HTTPException returns JSON when the client expects JSON."""
    response = await auth_client.post(
        f"/entities/{uuid.uuid4()}/delete",
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]
    assert response.json()["detail"] == "Entity not found"


@pytest.mark.asyncio
async def test_validation_error_html(auth_client: AsyncClient):
    """A 422 (RequestValidationError) renders an HTML error page for browsers."""
    response = await auth_client.post(
        "/diets/api",
        json={"name": ""},  # min_length=1 → 422
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_validation_error_json(auth_client: AsyncClient):
    """A 422 returns structured JSON for API clients."""
    response = await auth_client.post(
        "/diets/api",
        json={"name": ""},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 422
    assert "application/json" in response.headers["content-type"]
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_error_page_has_home_link(auth_client: AsyncClient):
    """The HTML error page includes a dashboard link and localized title."""
    response = await auth_client.get("/nope", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "/dashboard" in response.text
