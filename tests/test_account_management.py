"""Account profile and administrator user-management controls."""

from datetime import UTC, datetime

import pytest

from app.auth import hash_password, verify_password
from app.models.user import User

pytestmark = pytest.mark.anyio


async def _managed_user(db_session) -> User:
    user = User(email="managed@example.com", password_hash=hash_password("managed-old"), role="user")
    db_session.add(user)
    await db_session.flush()
    return user


async def test_account_page_shows_identity_without_password_data(auth_client, test_user):
    response = await auth_client.get("/account")
    assert response.status_code == 200
    assert test_user.email in response.text
    assert test_user.password_hash not in response.text
    assert "/settings#password-h" in response.text


async def test_disabled_user_cookie_is_rejected(auth_client, db_session, test_user):
    test_user.disabled_at = datetime.now(UTC)
    db_session.add(test_user)
    await db_session.flush()
    response = await auth_client.get("/account")
    assert response.status_code == 401


async def test_admin_can_change_role_and_disable_user(auth_client, db_session, test_user):
    test_user.role = "admin"
    managed = await _managed_user(db_session)

    response = await auth_client.post(f"/admin/users/{managed.id}/role", data={"role": "moderator"})
    assert response.status_code == 303
    await db_session.refresh(managed)
    assert managed.role == "moderator"

    response = await auth_client.post(f"/admin/users/{managed.id}/disabled", data={"disabled": "true"})
    assert response.status_code == 303
    await db_session.refresh(managed)
    assert managed.disabled_at is not None


async def test_admin_cannot_disable_or_demote_self(auth_client, db_session, test_user):
    test_user.role = "admin"
    response = await auth_client.post(f"/admin/users/{test_user.id}/disabled", data={"disabled": "true"})
    assert response.status_code == 409
    response = await auth_client.post(f"/admin/users/{test_user.id}/role", data={"role": "user"})
    assert response.status_code == 409


async def test_admin_can_reset_other_password(auth_client, db_session, test_user):
    test_user.role = "admin"
    managed = await _managed_user(db_session)
    response = await auth_client.post(
        f"/admin/users/{managed.id}/password",
        data={"new_password": "managed-new", "confirm_password": "managed-new"},
    )
    assert response.status_code == 303
    await db_session.refresh(managed)
    assert verify_password("managed-new", managed.password_hash)
    assert not verify_password("managed-old", managed.password_hash)


async def test_regular_user_cannot_list_users(auth_client):
    response = await auth_client.get("/admin/users")
    assert response.status_code == 403
