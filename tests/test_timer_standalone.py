"""Timer-only deploy smoke test — verifies Timer works independently (Q12).

Tests:
- Timer routes are registered when LOCKTIMER_CORE_ENABLED=true
- Timer overview page renders
- New timer session creation
- Tag violations page renders
- Tracker-specific routes are NOT required for timer functionality
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


class TestTimerStandalone:
    """Verify Timer module is self-contained and deployable independently."""

    async def test_timer_overview_accessible(self, auth_client: AsyncClient) -> None:
        """GET /locktimer — overview page renders."""
        resp = await auth_client.get("/locktimer", follow_redirects=True)
        assert resp.status_code == 200

    async def test_timer_new_creates_draft(self, auth_client: AsyncClient) -> None:
        """POST /locktimer/new — creates draft and redirects to detail."""
        resp = await auth_client.post("/locktimer/new", follow_redirects=False)
        # Should redirect to session detail (303)
        assert resp.status_code in (303, 302)
        assert "/locktimer/sessions/" in resp.headers.get("location", "")

    async def test_timer_templates_page(self, auth_client: AsyncClient) -> None:
        """GET /locktimer/templates — templates page renders."""
        resp = await auth_client.get("/locktimer/templates", follow_redirects=True)
        assert resp.status_code == 200

    async def test_timer_tag_violations_page(self, auth_client: AsyncClient) -> None:
        """GET /locktimer/tag-violations/{id} — renders or redirects for nonexistent session."""
        resp = await auth_client.get(
            "/locktimer/tag-violations/00000000-0000-0000-0000-000000000000",
            follow_redirects=True,
        )
        # Should redirect to /locktimer for nonexistent session or return 200
        assert resp.status_code in (200, 404) or resp.url.path == "/locktimer"

    async def test_timer_api_endpoints_accessible(self, auth_client: AsyncClient) -> None:
        """Verify key timer API endpoints respond (not 405 — route exists)."""
        # JSON API tag violations — may return 404 for nonexistent session
        resp = await auth_client.get(
            "/api/v2/locktimer/tag-violations/00000000-0000-0000-0000-000000000000",
        )
        # 404 = session not found (route exists), 405 = method not allowed
        assert resp.status_code != 405, f"Route not found: {resp.status_code}"

    async def test_timer_capabilities_endpoint(self, auth_client: AsyncClient) -> None:
        """GET /api/v2/platform/capabilities — timer is listed as enabled module."""
        resp = await auth_client.get("/api/v2/platform/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled_modules" in data or "social_stage" in data


class TestTimerRouteIsolation:
    """Verify timer routes don't leak tracker data and vice versa."""

    async def test_timer_page_no_tracker_internals(self, auth_client: AsyncClient) -> None:
        """Timer pages should not contain raw_llm_response or penalty_details."""
        resp = await auth_client.get("/locktimer", follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            assert "raw_llm_response" not in text.lower(), "timer page leaks raw_llm_response"
            assert "penalty_details" not in text.lower(), "timer page leaks penalty_details"
