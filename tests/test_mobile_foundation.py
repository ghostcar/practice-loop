"""Mobile Foundation (M4) tests.

Covers the JSON bearer-auth contract (access + refresh, rotation + revocation),
push-device registration, the dual-mode JSON-first action responses, and the
``token_type`` claim that keeps refresh JWTs out of the access path.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token, hash_password
from app.config import settings
from app.locktimer import enums as e
from app.locktimer.services.execution import add_slot_rule, create_draft
from app.models.api_token import ApiToken
from app.models.user import User


async def _bearer_token(client: AsyncClient, email: str = "test@example.com", password: str = "secret123") -> str:
    resp = await client.post("/api/v2/auth/token", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token issuance + access
# ---------------------------------------------------------------------------


async def test_token_issue_and_access(async_client: AsyncClient, test_user: User) -> None:
    resp = await async_client.post(
        "/api/v2/auth/token",
        json={"email": "test@example.com", "password": "secret123", "client_name": "pixel", "platform": "android"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_in"] == settings.jwt_expire_minutes * 60

    me = await async_client.get("/api/v2/auth/me", headers=_bearer(data["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


async def test_token_invalid_credentials(async_client: AsyncClient, test_user: User) -> None:
    resp = await async_client.post("/api/v2/auth/token", json={"email": "test@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_me_requires_auth(async_client: AsyncClient, test_user: User) -> None:
    resp = await async_client.get("/api/v2/auth/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh rotation + revocation
# ---------------------------------------------------------------------------


async def test_refresh_rotates_and_old_token_dies(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession
) -> None:
    issue = await async_client.post("/api/v2/auth/token", json={"email": "test@example.com", "password": "secret123"})
    refresh1 = issue.json()["refresh_token"]

    r2 = await async_client.post("/api/v2/auth/refresh", json={"refresh_token": refresh1})
    assert r2.status_code == 200
    refresh2 = r2.json()["refresh_token"]
    assert refresh2 != refresh1

    # Old refresh is revoked by rotation.
    r3 = await async_client.post("/api/v2/auth/refresh", json={"refresh_token": refresh1})
    assert r3.status_code == 401

    # Exactly one revoked + one active token in the table (rotation chain).
    tokens = (await db_session.execute(select(ApiToken))).scalars().all()
    assert len(tokens) == 2
    assert sum(1 for t in tokens if t.revoked_at is not None) == 1
    active = [t for t in tokens if t.revoked_at is None][0]
    assert active.rotated_from_id is not None


async def test_revoke_by_value(async_client: AsyncClient, test_user: User) -> None:
    issue = await async_client.post("/api/v2/auth/token", json={"email": "test@example.com", "password": "secret123"})
    refresh = issue.json()["refresh_token"]

    rev = await async_client.post("/api/v2/auth/revoke", json={"refresh_token": refresh})
    assert rev.status_code == 200

    r = await async_client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_list_and_revoke_by_id(async_client: AsyncClient, test_user: User) -> None:
    token = await _bearer_token(async_client)

    listing = await async_client.get("/api/v2/auth/tokens", headers=_bearer(token))
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["revoked"] is False

    rev = await async_client.post(f"/api/v2/auth/tokens/{items[0]['id']}/revoke", headers=_bearer(token))
    assert rev.status_code == 200

    listing2 = await async_client.get("/api/v2/auth/tokens", headers=_bearer(token))
    assert listing2.json()[0]["revoked"] is True


async def test_refresh_token_cannot_be_used_as_access(async_client: AsyncClient, test_user: User) -> None:
    issue = await async_client.post("/api/v2/auth/token", json={"email": "test@example.com", "password": "secret123"})
    refresh = issue.json()["refresh_token"]

    # An opaque refresh token is not a valid access JWT.
    resp = await async_client.get("/api/v2/auth/me", headers=_bearer(refresh))
    assert resp.status_code == 401


async def test_token_type_claim_rejects_non_access_jwt() -> None:
    """A JWT minted for a different purpose must not authenticate as access."""
    other = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(other) is None


# ---------------------------------------------------------------------------
# Push devices
# ---------------------------------------------------------------------------


async def test_push_device_register_list_deactivate(async_client: AsyncClient, test_user: User) -> None:
    token = await _bearer_token(async_client)

    reg = await async_client.post(
        "/api/v2/push/devices",
        json={"platform": "fcm_android", "device_token": "tok-abc", "app_version": "1.0.0"},
        headers=_bearer(token),
    )
    assert reg.status_code == 201
    assert reg.json()["platform"] == "fcm_android"
    assert reg.json()["is_active"] is True

    # Re-registering the same token re-activates (idempotent).
    reg2 = await async_client.post(
        "/api/v2/push/devices",
        json={"platform": "fcm_android", "device_token": "tok-abc"},
        headers=_bearer(token),
    )
    assert reg2.status_code == 201
    assert reg2.json()["id"] == reg.json()["id"]

    listing = await async_client.get("/api/v2/push/devices", headers=_bearer(token))
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    dev_id = listing.json()[0]["id"]
    deact = await async_client.post(f"/api/v2/push/devices/{dev_id}/deactivate", headers=_bearer(token))
    assert deact.status_code == 200

    listing2 = await async_client.get("/api/v2/push/devices", headers=_bearer(token))
    assert listing2.json()[0]["is_active"] is False


async def test_push_device_cross_user_isolation(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession
) -> None:
    token = await _bearer_token(async_client)

    reg = await async_client.post(
        "/api/v2/push/devices",
        json={"platform": "apns_ios", "device_token": "tok-ios"},
        headers=_bearer(token),
    )
    dev_id = reg.json()["id"]

    other = User(email="other@example.com", password_hash=hash_password("secret123"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_token = await _bearer_token(async_client, email="other@example.com")

    # Other user sees an empty device list and cannot delete our device.
    other_list = await async_client.get("/api/v2/push/devices", headers=_bearer(other_token))
    assert other_list.status_code == 200
    assert other_list.json() == []

    other_del = await async_client.delete(f"/api/v2/push/devices/{dev_id}", headers=_bearer(other_token))
    assert other_del.status_code == 404


async def test_push_device_rejects_unknown_platform(async_client: AsyncClient, test_user: User) -> None:
    token = await _bearer_token(async_client)
    resp = await async_client.post(
        "/api/v2/push/devices",
        json={"platform": "windows", "device_token": "tok"},
        headers=_bearer(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Dual-mode JSON-first action responses (ADR-065)
# ---------------------------------------------------------------------------


async def _make_draft(db_session: AsyncSession, user_id: uuid.UUID):
    draft = await create_draft(db_session, owner_id=user_id, timezone_str="UTC")
    await add_slot_rule(
        db_session,
        session_id=draft.id,
        name="Daily",
        rule_type=e.SLOT_RULE_EVERY_N_DAYS,
        schedule={"n": 1, "time_of_day": "09:00"},
        duration_seconds=1800,
    )
    await db_session.flush()
    return draft


async def test_locktimer_start_bearer_json(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession
) -> None:
    draft = await _make_draft(db_session, test_user.id)
    token = await _bearer_token(async_client)

    resp = await async_client.post(f"/api/v2/locktimer/sessions/{draft.id}/start", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["status"] == "started"
    assert body["session_id"] == str(draft.id)


async def test_locktimer_start_cookie_redirect(
    async_client: AsyncClient, test_user: User, db_session: AsyncSession, auth_headers: dict
) -> None:
    draft = await _make_draft(db_session, test_user.id)

    resp = await async_client.post(f"/api/v2/locktimer/sessions/{draft.id}/start", headers=auth_headers)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/locktimer/sessions/{draft.id}"


# ---------------------------------------------------------------------------
# Media URL contract (bearer) — JSON list + authorized serve
# ---------------------------------------------------------------------------


async def test_media_list_bearer(async_client: AsyncClient, test_user: User) -> None:
    token = await _bearer_token(async_client)
    resp = await async_client.get("/api/v2/media", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json() == []
