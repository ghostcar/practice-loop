"""Tests for C3 — Consent records (согласия на чувствительную обработку).

Явные согласия (granted/revoked) с версионированием: каждое изменение —
новая запись, история не перезаписывается. Relief-only (PD-013).
"""

from __future__ import annotations

import pytest

from app.models.consent import ConsentRecord


@pytest.mark.asyncio
async def test_json_grant_then_revoke_versions(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/consent",
        json={"consent_type": "llm_expanded", "state": "granted", "scope": "detailed lab analysis"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["state"] == "granted"
    assert body["version"] == 1

    # revoke → new version
    resp2 = await auth_client.post(
        "/api/v2/consent",
        json={"consent_type": "llm_expanded", "state": "revoked"},
    )
    assert resp2.status_code == 201
    assert resp2.json()["version"] == 2
    assert resp2.json()["revoked_at"] is not None

    listed = (await auth_client.get("/api/v2/consent")).json()
    assert len(listed["records"]) == 2
    # latest (highest version first) is the revoked one
    assert listed["latest"]["llm_expanded"]["state"] == "revoked"


@pytest.mark.asyncio
async def test_json_invalid_type_and_state(auth_client, test_user, db_session):
    r1 = await auth_client.post("/api/v2/consent", json={"consent_type": "bogus", "state": "granted"})
    assert r1.status_code == 400
    r2 = await auth_client.post("/api/v2/consent", json={"consent_type": "custom", "state": "bogus"})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_json_filter_and_delete(auth_client, test_user, db_session):
    await auth_client.post("/api/v2/consent", json={"consent_type": "data_processing", "state": "granted"})
    await auth_client.post("/api/v2/consent", json={"consent_type": "media_verification", "state": "granted"})

    filtered = (await auth_client.get("/api/v2/consent?consent_type=data_processing")).json()
    assert len(filtered["records"]) == 1

    rec_id = filtered["records"][0]["id"]
    assert (await auth_client.delete(f"/api/v2/consent/{rec_id}")).status_code == 204
    assert (await auth_client.get("/api/v2/consent?consent_type=data_processing")).json()["records"] == []


@pytest.mark.asyncio
async def test_form_handler_adds_record(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/consent",
        data={"consent_type": "media_verification", "state": "granted", "scope": "photo to LLM"},
    )
    assert resp.status_code == 303
    latest = (await auth_client.get("/api/v2/consent")).json()["latest"]
    assert latest["media_verification"]["state"] == "granted"


@pytest.mark.asyncio
async def test_page_renders(auth_client, test_user, db_session):
    resp = await auth_client.get("/consent")
    assert resp.status_code == 200
    assert "consent" in resp.text.lower()


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    from app.models.user import User

    db_session.add(ConsentRecord(user_id=test_user.id, consent_type="custom", state="granted", version=1))
    await db_session.flush()

    other = User(email="other-consent@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    assert (await auth_client.get("/api/v2/consent")).json()["records"] == []
