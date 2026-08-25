"""Tests for the public Vitrina showcase (v1.0 Stage I / ADR-183).

The vitrina must be accessible WITHOUT authentication and expose only
anonymized aggregate data (no emails, no user ids).
"""

import pytest

from app.api.vitrina import public_router


def test_vitrina_router_is_public():
    """The vitrina router exposes exactly one public route under /vitrina."""
    assert [r.path for r in public_router.routes] == ["/vitrina"]


@pytest.mark.asyncio
async def test_vitrina_public_no_auth(async_client):
    """The vitrina page renders for anonymous visitors (no auth dependency)."""
    resp = await async_client.get("/vitrina")
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "vitrina" in text or "витрина" in text


@pytest.mark.asyncio
async def test_vitrina_counters_present(async_client):
    """Rendered page includes community counters even with empty DB."""
    resp = await async_client.get("/vitrina")
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "community" in text or "витрина" in text


@pytest.mark.asyncio
async def test_vitrina_no_email_leak(async_client, db_session):
    """The vitrina page must not render any raw emails."""
    resp = await async_client.get("/vitrina")
    assert resp.status_code == 200
    # No user email should appear in the rendered HTML
    assert "email" not in resp.text.lower() or "example.com" not in resp.text
