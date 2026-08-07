"""Integration tests for Telegram bot commands and handlers.

Tests bot command logic via the web profile endpoints (link code generation,
status check) plus unit-level tests for bot utility functions.
Full polling/webhook tests are skipped because they require a real bot token.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# ── Telegram link code lifecycle (via web API) ─────────────────────


@pytest.mark.asyncio
async def test_generate_link_code(auth_client: AsyncClient, test_user: User) -> None:
    """POST /profile/telegram-link-code generates a 6-char code."""
    response = await auth_client.post("/profile/telegram-link-code")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert len(data["code"]) == 6
    assert data["code"].isalnum()
    assert data["code"] == data["code"].upper()


@pytest.mark.asyncio
async def test_link_code_is_stored(auth_client: AsyncClient, db_session: AsyncSession, test_user: User) -> None:
    """After generating, the code is stored on the user record."""
    response = await auth_client.post("/profile/telegram-link-code")
    assert response.status_code == 200
    code = response.json()["code"]

    await db_session.refresh(test_user)
    assert test_user.telegram_link_code == code
    assert test_user.telegram_link_code_expires is not None
    # Should expire ~30 minutes from now (SQLite stores naive, compare naive)
    assert test_user.telegram_link_code_expires is not None
    assert test_user.telegram_link_code_expires > datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_link_code_expiry_window(auth_client: AsyncClient, db_session: AsyncSession, test_user: User) -> None:
    """Link code expires within ~30 minutes."""
    response = await auth_client.post("/profile/telegram-link-code")
    assert response.json()["code"]  # code is present

    await db_session.refresh(test_user)
    expires = test_user.telegram_link_code_expires
    now = datetime.now(UTC).replace(tzinfo=None)
    delta = (expires - now).total_seconds()
    # Should be between 25 and 35 minutes (allow some clock skew)
    assert 25 * 60 < delta < 35 * 60, f"Expiry delta {delta}s not in 25-35min range"


@pytest.mark.asyncio
async def test_telegram_status_not_linked(auth_client: AsyncClient) -> None:
    """Status shows not linked before linking."""
    response = await auth_client.get("/profile/telegram-status")
    assert response.status_code == 200
    data = response.json()
    assert data["linked"] is False


@pytest.mark.asyncio
async def test_telegram_status_after_simulated_link(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
) -> None:
    """Status shows linked after chat_id is set (simulating successful /link)."""
    # Simulate what the /link command does
    test_user.telegram_chat_id = 123456789
    test_user.telegram_link_code = None
    test_user.telegram_link_code_expires = None
    db_session.add(test_user)
    await db_session.flush()

    response = await auth_client.get("/profile/telegram-status")
    assert response.status_code == 200
    data = response.json()
    assert data["linked"] is True


# ── Bot utility: _get_user_by_chat logic (DB query) ────────────────


@pytest.mark.asyncio
async def test_bot_get_user_by_chat_found(db_session: AsyncSession, test_user: User) -> None:
    """Querying User by telegram_chat_id finds the linked user."""
    from sqlalchemy import select

    test_user.telegram_chat_id = 111222333
    db_session.add(test_user)
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.telegram_chat_id == 111222333))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.id == test_user.id


@pytest.mark.asyncio
async def test_bot_get_user_by_chat_not_found(db_session: AsyncSession) -> None:
    """Querying by unknown chat_id returns None."""
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.telegram_chat_id == 999999999))
    user = result.scalar_one_or_none()
    assert user is None


# ── Bot utility: _require_user logic ───────────────────────────────


@pytest.mark.asyncio
async def test_bot_require_user_linked(db_session: AsyncSession, test_user: User) -> None:
    """Linked user is found by chat_id; unlinked users get None."""
    from sqlalchemy import select

    # Link the user
    test_user.telegram_chat_id = 444555666
    db_session.add(test_user)
    await db_session.flush()

    # Simulate _require_user logic: find by chat_id
    result = await db_session.execute(select(User).where(User.telegram_chat_id == 444555666))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.id == test_user.id

    # Unlinked user returns None
    result = await db_session.execute(select(User).where(User.telegram_chat_id == 999999999))
    assert result.scalar_one_or_none() is None


# ── Webhook endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_unauthorized_without_secret(async_client: AsyncClient) -> None:
    """Webhook returns 'bot not configured' or 'unauthorized' without proper secret."""
    response = await async_client.post("/tg/webhook", json={"update_id": 1})
    assert response.status_code == 200
    data = response.json()
    # Without TG_BOT_TOKEN: "bot not configured"; with token but no secret: "unauthorized"
    assert data["status"] in ("bot not configured", "unauthorized")


@pytest.mark.asyncio
async def test_webhook_with_secret(async_client: AsyncClient) -> None:
    """Webhook with correct secret accepts the update (may be 'bot not configured' but not 401)."""
    response = await async_client.post(
        "/tg/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "change-me"},
    )
    assert response.status_code == 200
    data = response.json()
    # Without a real bot token, status will be "bot not configured"
    assert data["status"] in ("bot not configured", "ok")


# ── send_telegram_notification ─────────────────────────────────────


@pytest.mark.asyncio
async def test_send_notification_without_bot() -> None:
    """send_telegram_notification returns False when bot is not configured."""
    from app.telegram.bot import send_telegram_notification

    result = await send_telegram_notification(chat_id=123, text="Hello")
    assert result is False  # Bot is None in test environment


# ── Cross-user: link code isolation ─────────────────────────────────


@pytest.mark.asyncio
async def test_link_code_is_user_scoped(auth_client: AsyncClient, db_session: AsyncSession, test_user: User) -> None:
    """Each user's link code is unique and scoped to them."""
    from app.auth import hash_password

    # Create second user
    other = User(
        email="other-tg@example.com",
        password_hash=hash_password("secret123"),
        locale="en",
        theme="dark",
    )
    db_session.add(other)
    await db_session.flush()

    # Generate code for test_user via API (POST)
    resp1 = await auth_client.post("/profile/telegram-link-code")
    code1 = resp1.json()["code"]

    await db_session.refresh(test_user)
    assert test_user.telegram_link_code == code1

    # Second user should not have a code yet
    assert other.telegram_link_code is None

    # Verify codes are stored separately
    assert test_user.telegram_link_code != other.telegram_link_code
