"""Unit and integration tests for Telegram linking flow (ADR-194).

Covers:
- 1-Click Deep link generation & active code caching
- QR SVG generation via zxing-cpp
- Bot OTP generation (/connect) & consumption on portal
- Unlinking flow (HTTP & bot command)
- HTTP endpoints: /profile, /profile/telegram-qr, /profile/telegram-link-by-otp, /profile/telegram-unlink
- Deep link resolution in telegram bot
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import telegram_link_service as tg_link_svc
from app.telegram.personal_contour import _try_link_by_code


@pytest.mark.asyncio
async def test_generate_user_telegram_link_code(db_session: AsyncSession, test_user: User):
    """Generates 6-char link code and deep link URL."""
    res = await tg_link_svc.generate_user_telegram_link_code(db_session, test_user)
    assert len(res["code"]) == 6
    assert res["code"].isalnum()
    assert res["deep_link_url"].startswith("https://t.me/")
    assert f"start=link_{res['code']}" in res["deep_link_url"]

    # Verify stored in DB
    await db_session.refresh(test_user)
    assert test_user.telegram_link_code == res["code"]
    assert test_user.telegram_link_code_expires is not None


@pytest.mark.asyncio
async def test_ensure_active_link_code_reuses_valid(db_session: AsyncSession, test_user: User):
    """ensure_active_link_code preserves valid unexpired code."""
    code1, url1 = await tg_link_svc.ensure_active_link_code(db_session, test_user)
    code2, url2 = await tg_link_svc.ensure_active_link_code(db_session, test_user)
    assert code1 == code2
    assert url1 == url2


def test_generate_telegram_qr_svg():
    """Generates valid SVG string for telegram link."""
    svg = tg_link_svc.generate_telegram_qr_svg("https://t.me/practice_loop_bot?start=link_TEST1234")
    assert "<svg" in svg
    assert "</svg>" in svg


@pytest.mark.asyncio
async def test_bot_otp_creation_and_linking(db_session: AsyncSession, test_user: User):
    """Bot generates 6-digit OTP and web portal consumes it to link user."""
    chat_id = 9988776655
    otp = tg_link_svc.create_bot_connect_code(chat_id=chat_id, username="tester_tg", first_name="Tester")
    assert len(otp) == 6
    assert otp.isdigit()

    # Link with valid code
    ok, msg, linked_chat = await tg_link_svc.link_user_by_bot_otp(db_session, test_user, otp)
    assert ok is True
    assert linked_chat == chat_id
    assert test_user.telegram_chat_id == chat_id

    # Code must be consumed (one-time)
    ok2, _, _ = await tg_link_svc.link_user_by_bot_otp(db_session, test_user, otp)
    assert ok2 is False


@pytest.mark.asyncio
async def test_bot_otp_expired_code(db_session: AsyncSession, test_user: User):
    """Expired bot OTP returns false."""
    chat_id = 11223344
    otp = tg_link_svc.create_bot_connect_code(chat_id=chat_id, ttl_minutes=-1)  # expired immediately
    ok, msg, _ = await tg_link_svc.link_user_by_bot_otp(db_session, test_user, otp)
    assert ok is False
    assert "истёк" in msg or "устаревший" in msg


@pytest.mark.asyncio
async def test_unlink_user_telegram(db_session: AsyncSession, test_user: User):
    """Unlinking resets telegram_chat_id and codes."""
    test_user.telegram_chat_id = 555666
    test_user.telegram_link_code = "XYZ123"
    test_user.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=10)
    db_session.add(test_user)
    await db_session.commit()

    old_chat = await tg_link_svc.unlink_user_telegram(db_session, test_user)
    assert old_chat == 555666
    assert test_user.telegram_chat_id is None
    assert test_user.telegram_link_code is None


@pytest.mark.asyncio
async def test_try_link_by_code_telegram_bot(db_session: AsyncSession, test_user: User):
    """Telegram bot resolves link_<code> parameter directly into account linking."""
    test_user.telegram_link_code = "ABCDEF12"
    test_user.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=15)
    db_session.add(test_user)
    await db_session.commit()

    mock_msg = MagicMock()
    mock_msg.chat.id = 123456789
    mock_msg.answer = AsyncMock()

    # Pass with link_ prefix and db session
    linked = await _try_link_by_code(mock_msg, "link_ABCDEF12", db=db_session)
    assert linked is True

    # User in DB is updated
    updated_user = (await db_session.execute(select(User).where(User.id == test_user.id))).scalar_one()
    assert updated_user.telegram_chat_id == 123456789
    assert updated_user.telegram_link_code is None
    mock_msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_http_profile_page_includes_telegram_data(auth_client: AsyncClient, test_user: User):
    """Profile page renders Telegram integration card."""
    res = await auth_client.get("/profile")
    assert res.status_code == 200
    assert "Telegram" in res.text
    assert "telegram-qr" in res.text
    assert "Подключить" in res.text


@pytest.mark.asyncio
async def test_http_profile_telegram_qr_endpoint(auth_client: AsyncClient, test_user: User):
    """GET /profile/telegram-qr returns clean SVG barcode."""
    res = await auth_client.get("/profile/telegram-qr")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in res.text
    assert "</svg>" in res.text


@pytest.mark.asyncio
async def test_http_profile_link_by_otp_endpoint(auth_client: AsyncClient, test_user: User, db_session: AsyncSession):
    """POST /profile/telegram-link-by-otp links account via 6-digit OTP."""
    otp = tg_link_svc.create_bot_connect_code(chat_id=777888999)

    res = await auth_client.post(
        "/profile/telegram-link-by-otp",
        data={"otp_code": otp},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "status=tg_linked" in res.headers["location"]

    await db_session.refresh(test_user)
    assert test_user.telegram_chat_id == 777888999


@pytest.mark.asyncio
async def test_http_profile_unlink_endpoint(auth_client: AsyncClient, test_user: User, db_session: AsyncSession):
    """POST /profile/telegram-unlink unlinks user."""
    test_user.telegram_chat_id = 777888999
    db_session.add(test_user)
    await db_session.commit()

    res = await auth_client.post("/profile/telegram-unlink", follow_redirects=False)
    assert res.status_code == 303
    assert "status=tg_unlinked" in res.headers["location"]

    await db_session.refresh(test_user)
    assert test_user.telegram_chat_id is None
