"""Telegram linking service (ADR-194).

Provides seamless Telegram-to-Portal account linking:
- 1-Click Deep Links (t.me/<bot>?start=link_<code>)
- Standalone SVG QR-code generation via zxing-cpp
- Bidirectional One-Time Passwords (OTP):
  * Web -> Telegram (/link <code>)
  * Telegram -> Web (/connect -> 6-digit PIN input)
- Safe unlinking with notification hook
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.timeutils import as_utc

logger = logging.getLogger(__name__)

# In-memory storage for Telegram bot-generated OTP connect codes
# code -> {"chat_id": int, "username": str | None, "first_name": str | None, "expires_at": datetime}
_BOT_CONNECT_CODES: dict[str, dict] = {}


def _cleanup_expired_bot_codes() -> None:
    now = datetime.now(UTC)
    expired = [code for code, data in _BOT_CONNECT_CODES.items() if data["expires_at"] < now]
    for code in expired:
        _BOT_CONNECT_CODES.pop(code, None)


def create_bot_connect_code(
    chat_id: int,
    username: str | None = None,
    first_name: str | None = None,
    ttl_minutes: int = 10,
) -> str:
    """Generate a 6-digit numeric OTP in the Telegram bot to be entered on the web portal."""
    _cleanup_expired_bot_codes()

    # Generate unique 6-digit code
    for _ in range(20):
        code = f"{secrets.randbelow(900000) + 100000}"
        if code not in _BOT_CONNECT_CODES:
            break

    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    _BOT_CONNECT_CODES[code] = {
        "chat_id": chat_id,
        "username": username,
        "first_name": first_name,
        "expires_at": expires_at,
    }
    return code


async def link_user_by_bot_otp(
    db: AsyncSession,
    user: User,
    otp_code: str,
) -> tuple[bool, str, int | None]:
    """Link user account using a 6-digit OTP provided by Telegram bot."""
    _cleanup_expired_bot_codes()
    clean_code = otp_code.strip()

    entry = _BOT_CONNECT_CODES.get(clean_code)
    if not entry:
        return False, "Неверный или устаревший код подтверждения.", None

    if entry["expires_at"] < datetime.now(UTC):
        _BOT_CONNECT_CODES.pop(clean_code, None)
        return False, "Срок действия кода истёк. Запросите новый код в боте по команде /connect.", None

    chat_id = entry["chat_id"]

    # Check if this chat_id is already bound to another user
    existing_stmt = select(User).where(User.telegram_chat_id == chat_id, User.id != user.id)
    other_user = (await db.execute(existing_stmt)).scalar_one_or_none()
    if other_user:
        other_user.telegram_chat_id = None
        db.add(other_user)

    user.telegram_chat_id = chat_id
    user.telegram_link_code = None
    user.telegram_link_code_expires = None
    db.add(user)
    await db.flush()

    _BOT_CONNECT_CODES.pop(clean_code, None)
    return True, "Telegram успешно привязан!", chat_id


async def generate_user_telegram_link_code(
    db: AsyncSession,
    user: User,
    ttl_minutes: int = 30,
) -> dict:
    """Generate or renew web linking code and 1-click deep link URL."""
    code = secrets.token_hex(3).upper()  # 6-char hex code
    expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)

    user.telegram_link_code = code
    user.telegram_link_code_expires = expires
    db.add(user)
    await db.flush()

    bot_user = settings.tg_bot_username.lstrip("@")
    deep_link = f"https://t.me/{bot_user}?start=link_{code}"

    return {
        "code": code,
        "deep_link_url": deep_link,
        "expires_in_minutes": ttl_minutes,
        "bot_username": bot_user,
    }


async def ensure_active_link_code(
    db: AsyncSession,
    user: User,
) -> tuple[str, str]:
    """Ensure user has a valid unexpired link code, generating one if missing."""
    now = datetime.now(UTC)
    bot_user = settings.tg_bot_username.lstrip("@")

    if (
        user.telegram_link_code
        and user.telegram_link_code_expires
        and as_utc(user.telegram_link_code_expires) > now
    ):
        code = user.telegram_link_code
    else:
        info = await generate_user_telegram_link_code(db, user)
        code = info["code"]

    deep_link = f"https://t.me/{bot_user}?start=link_{code}"
    return code, deep_link


def generate_telegram_qr_svg(url: str) -> str:
    """Generate clean SVG QR-code using zxingcpp without external network calls."""
    try:
        import zxingcpp

        barcode = zxingcpp.create_barcode(url, zxingcpp.BarcodeFormat.QRCode)
        return zxingcpp.write_barcode_to_svg(barcode)
    except Exception as e:
        logger.warning("Failed to render QR-code with zxingcpp: %s", e)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="160" height="160">'
            '<rect width="100" height="100" fill="#f8fafc"/>'
            '<text x="50" y="55" font-size="10" text-anchor="middle" fill="#64748b">QR Error</text>'
            "</svg>"
        )


async def unlink_user_telegram(db: AsyncSession, user: User) -> int | None:
    """Unlink user's Telegram chat."""
    old_chat_id = user.telegram_chat_id
    user.telegram_chat_id = None
    user.telegram_link_code = None
    user.telegram_link_code_expires = None
    db.add(user)
    await db.flush()
    return old_chat_id
