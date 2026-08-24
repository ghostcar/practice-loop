"""Self-service password changes from the authenticated settings page."""

import pytest

from app.auth import verify_password

pytestmark = pytest.mark.anyio


async def test_settings_renders_password_form(auth_client):
    response = await auth_client.get("/settings?tab=security")
    assert response.status_code == 200
    assert 'action="/settings/password"' in response.text
    assert 'autocomplete="current-password"' in response.text


async def test_change_password_requires_current_password(auth_client, test_user):
    response = await auth_client.post(
        "/settings/password",
        data={"current_password": "wrong", "new_password": "new-secret", "confirm_password": "new-secret"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?password_status=invalid"
    assert verify_password("secret123", test_user.password_hash)


async def test_change_password_updates_hash(auth_client, db_session, test_user):
    response = await auth_client.post(
        "/settings/password",
        data={"current_password": "secret123", "new_password": "new-secret", "confirm_password": "new-secret"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?password_status=changed"
    await db_session.refresh(test_user)
    assert verify_password("new-secret", test_user.password_hash)
    assert not verify_password("secret123", test_user.password_hash)


@pytest.mark.parametrize(
    ("new_password", "confirm_password", "status"),
    [("short", "short", "length"), ("new-secret", "different", "mismatch"), ("secret123", "secret123", "same")],
)
async def test_change_password_rejects_invalid_new_password(
    auth_client, test_user, new_password, confirm_password, status
):
    response = await auth_client.post(
        "/settings/password",
        data={"current_password": "secret123", "new_password": new_password, "confirm_password": confirm_password},
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/settings?password_status={status}"
    assert verify_password("secret123", test_user.password_hash)
