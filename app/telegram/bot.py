"""Telegram bot — aiogram 3.x, webhook/polling, modular router dispatch."""

import asyncio
import contextlib
import logging
import uuid

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.user import User
from app.telegram.pc.helpers import (
    _SCAN_CACHE,
    _require_user,
    personal_router,
)

logger = logging.getLogger(__name__)

# --- Bot setup ---
TG_BOT_TOKEN = getattr(settings, "tg_bot_token", None)
TG_WEBHOOK_SECRET = getattr(settings, "tg_webhook_secret", "change-me")
TG_WEBHOOK_PATH = "/tg/webhook"

bot: Bot | None = None
dp: Dispatcher | None = None
tg_router = APIRouter(prefix="/tg", tags=["telegram"])
main_router = Router(name="main_legacy")


async def process_datamatrix_scan(message: types.Message, user: User, results: list) -> None:
    """Processes decoded DataMatrix results, looks up medicine, and presents kit selection."""
    from app.models.medication import MedKit
    from app.services import med_service as med_svc
    from app.services.pharma_online import online_drug_lookup

    first = results[0]
    gtin = first.gtin or ""
    ean13 = first.ean13 or ""
    lot = first.lot_number or ""
    expiry = first.expiry_date or ""
    serial = first.serial or ""

    async with async_session_factory() as db:
        med = await med_svc.find_medication_by_barcode(db, user.id, gtin=gtin, ean13=ean13)
        med_name = med.name if med else None

        if not med_name and (gtin or ean13):
            online_info = await online_drug_lookup(ean13 or gtin)
            if online_info and online_info.get("name"):
                med_name = online_info["name"]

        if not med_name:
            med_name = f"Препарат (GTIN: {gtin or ean13 or 'DataMatrix'})"

        stmt = select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name)
        kits = (await db.execute(stmt)).scalars().all()

    scan_id = uuid.uuid4().hex[:12]
    _SCAN_CACHE[scan_id] = {
        "user_id": str(user.id),
        "med_id": str(med.id) if med else None,
        "med_name": med_name,
        "lot": lot,
        "expiry": expiry,
        "gtin": gtin,
    }

    lines = [
        "📦 *Распознана маркировка (Честный Знак):*",
        f"💊 *Препарат:* {med_name}",
    ]
    if gtin:
        lines.append(f"🏷️ *GTIN:* `{gtin}`")
    if lot:
        lines.append(f"🔢 *Серия:* `{lot}`")
    if expiry:
        lines.append(f"📅 *Годен до:* `{expiry}`")
    if serial:
        lines.append(f"🔑 *SN:* `{serial[:12]}...`")

    lines.append("\nВыберите аптечку, куда добавить этот препарат:")

    kb_rows = []
    for k in kits[:6]:
        kb_rows.append([
            InlineKeyboardButton(text=f"📁 {k.name}", callback_data=f"dm_kit:{scan_id}:{k.id}")
        ])
    if not kits:
        lines.append("_(У вас пока нет созданных аптечек. Создайте аптечку на сайте в разделе медикаментов)_")

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


if TG_BOT_TOKEN:
    bot = Bot(token=TG_BOT_TOKEN)
    dp = Dispatcher()
    from app.telegram.agent_handler import agent_tg_router  # noqa: E402
    from app.telegram.community_handlers import (
        handle_ds_status_command,
        handle_my_rank_command,
        handle_tournaments_command,
    )

    dp.include_router(personal_router)
    dp.include_router(agent_tg_router)

    main_router.message(Command("tournaments"))(handle_tournaments_command)
    main_router.message(Command("my_rank"))(handle_my_rank_command)
    main_router.message(Command("ds_status"))(handle_ds_status_command)

    @main_router.message(Command("report"))
    async def cmd_report(message: types.Message):
        """Generates a 1-Click Medical & Personal Summary Report."""
        user = await _require_user(message)
        if user is None:
            return

        from app.llm.pipeline.persona import generate_personal_medical_report

        async with async_session_factory() as db:
            rep = await generate_personal_medical_report(db, user.id, days=30)

        await message.answer(rep["report_markdown"], parse_mode="Markdown")

    dp.include_router(main_router)


# ── Notification sender (public API for the rest of the app) ──────


async def send_telegram_notification(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to a Telegram user. Returns True on success."""
    if bot is None:
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.warning(f"Failed to send TG notification to chat {chat_id}", exc_info=True)
        return False


# ── Webhook endpoint ───────────────────────────────────────────────


@tg_router.post("/webhook")
async def tg_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    if dp is None or bot is None:
        return {"status": "bot not configured"}

    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != TG_WEBHOOK_SECRET:
        return {"status": "unauthorized"}

    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")

    return {"status": "ok"}


# ── Polling mode (local dev) ───────────────────────────────────────

_polling_task: asyncio.Task | None = None


async def start_polling() -> None:
    """Start long-polling for local development. Runs as a background task."""
    global _polling_task
    if bot is None or dp is None:
        logger.warning("Polling requested but bot not configured (missing tg_bot_token)")
        return

    # Delete any existing webhook to avoid conflicts
    await bot.delete_webhook(drop_pending_updates=True)

    _polling_task = asyncio.create_task(dp.start_polling(bot))
    logger.info("Telegram polling started (local dev mode)")


async def stop_polling() -> None:
    """Stop polling gracefully."""
    global _polling_task
    if _polling_task:
        _polling_task.cancel()
        with contextlib.suppress(Exception):
            await _polling_task
        _polling_task = None
        logger.info("Telegram polling stopped")


# ── Set webhook on startup ─────────────────────────────────────────


async def setup_webhook(base_url: str) -> str | None:
    """Register the webhook URL with Telegram. Called at app startup."""
    if bot is None:
        return None
    clean_base = base_url.rstrip("/")
    webhook_url = f"{clean_base}{TG_WEBHOOK_PATH}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=TG_WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info(f"Telegram webhook set to {webhook_url}")
        return webhook_url
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return None
