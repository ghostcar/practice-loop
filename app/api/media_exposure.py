"""API Router for Media Showcase, Dynamic Timer & Permanent Immutable Drops."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.media_exposure import MediaExposureDrop
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media/exposure", tags=["media_exposure"])
public_router = APIRouter(tags=["media_showcase_public"])


class ExposureCreateRequest(BaseModel):
    media_path: str = Field(..., description="Path to encrypted media")
    exposure_type: str = Field(default="dynamic_timer", description="one_time | dynamic_timer | permanent_immutable")
    initial_duration_minutes: int = Field(default=60, ge=1, le=10080)
    title: str | None = Field(default=None, max_length=255)
    caption: str | None = Field(default=None)
    pin_code: str | None = Field(default=None, max_length=16)


@router.post("/create")
async def create_media_exposure_drop(
    payload: ExposureCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new exposure drop: one_time, dynamic_timer, or permanent_immutable."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)

    pin_hash = None
    if payload.pin_code:
        pin_hash = hashlib.sha256(payload.pin_code.strip().encode("utf-8")).hexdigest()

    is_perm = payload.exposure_type == "permanent_immutable"
    expires_at = None
    if not is_perm:
        expires_at = now + timedelta(minutes=payload.initial_duration_minutes)

    drop = MediaExposureDrop(
        user_id=user.id,
        media_path=payload.media_path,
        token=token,
        title=payload.title or ("Неснимаемая Публикация" if is_perm else "Временная Экспозиция"),
        caption=payload.caption,
        exposure_type=payload.exposure_type,
        initial_duration_minutes=payload.initial_duration_minutes,
        expires_at=expires_at,
        pin_code_hash=pin_hash,
        is_permanent_immutable=is_perm,
        is_burned=False,
        view_count=0,
        extension_history=[
            {
                "action": "created",
                "exposure_type": payload.exposure_type,
                "initial_minutes": payload.initial_duration_minutes,
                "timestamp": now.isoformat(),
            }
        ],
    )
    db.add(drop)
    await db.flush()

    return JSONResponse(
        {
            "status": "success",
            "token": token,
            "exposure_type": payload.exposure_type,
            "showcase_url": f"/media/showcase/{token}",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "is_permanent_immutable": is_perm,
            "message": "Публикация успешно создана."
            + (" Внимание: данный снимок зафиксирован бессрочно и не может быть удален." if is_perm else ""),
        }
    )


@router.post("/{token}/adjust-timer")
async def adjust_exposure_timer(
    token: str,
    delta_minutes: int = Form(..., description="Minutes to add or subtract (e.g. +15, +60, -30)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dynamically extends (+X min) or reduces (-X min) the exposure duration."""
    stmt = select(MediaExposureDrop).where(MediaExposureDrop.token == token)
    drop = (await db.execute(stmt)).scalar_one_or_none()

    if not drop:
        raise HTTPException(404, "Экспозиция не найдена.")

    if drop.is_permanent_immutable:
        raise HTTPException(400, "Время постоянной публикации не может быть изменено.")

    if drop.is_burned:
        raise HTTPException(410, "Экспозиция уже уничтожена.")

    now = datetime.now(UTC)
    current_exp = drop.expires_at or now
    if current_exp.tzinfo is None:
        current_exp = current_exp.replace(tzinfo=UTC)

    new_exp = current_exp + timedelta(minutes=delta_minutes)
    if new_exp <= now:
        drop.is_burned = True
        new_exp = now

    drop.expires_at = new_exp
    history = list(drop.extension_history or [])
    history.append(
        {
            "action": "adjust_timer",
            "delta_minutes": delta_minutes,
            "adjusted_by": str(user.id),
            "new_expires_at": new_exp.isoformat(),
            "timestamp": now.isoformat(),
        }
    )
    drop.extension_history = history
    await db.flush()

    return JSONResponse(
        {
            "status": "success",
            "token": token,
            "delta_minutes": delta_minutes,
            "message": (
                f"Таймер экспозиции скорректирован на {delta_minutes:+d} мин. "
                f"Новый дедлайн: {new_exp.strftime('%H:%M:%S UTC')}."
            ),
        }
    )


@router.post("/{token}/revoke")
async def revoke_exposure_drop(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kill Switch: instantly destroys a temporary exposure drop."""
    stmt = select(MediaExposureDrop).where(
        MediaExposureDrop.token == token,
        MediaExposureDrop.user_id == user.id,
    )
    drop = (await db.execute(stmt)).scalar_one_or_none()

    if not drop:
        raise HTTPException(404, "Экспозиция не найдена.")

    if drop.is_permanent_immutable:
        raise HTTPException(403, "Запрещено: Неизменяемая постоянная публикация не может быть отозвана.")

    drop.is_burned = True
    drop.expires_at = datetime.now(UTC)
    await db.flush()

    return JSONResponse(
        {
            "status": "revoked",
            "token": token,
            "message": "Экспозиция успешно отозвана и уничтожена.",
        }
    )


@public_router.get("/media/showcase/{token}", response_class=HTMLResponse)
async def view_showcase_drop_page(
    request: Request,
    token: str,
    pin: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Public viewer page for Showcase drops with countdown timer, PIN protection, or permanent badge."""
    stmt = select(MediaExposureDrop).where(MediaExposureDrop.token == token)
    drop = (await db.execute(stmt)).scalar_one_or_none()

    locale = detect_locale(request, "ru")
    theme = "dark"
    t = get_translations(locale)

    if not drop:
        return templates.TemplateResponse(
            "media_showcase_item.html",
            {
                "request": request,
                "error": "Ссылка недействительна или файл уже удален.",
                "t": t,
                "theme": theme,
            },
            status_code=404,
        )

    now = datetime.now(UTC)

    # Check expiration
    if not drop.is_permanent_immutable and drop.expires_at:
        exp = drop.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if now > exp:
            drop.is_burned = True
            await db.flush()
            return templates.TemplateResponse(
                "media_showcase_item.html",
                {
                    "request": request,
                    "error": "Время экспозиции истекло. Снимок автоматически скрыт.",
                    "t": t,
                    "theme": theme,
                },
                status_code=410,
            )

    if drop.is_burned and not drop.is_permanent_immutable:
        return templates.TemplateResponse(
            "media_showcase_item.html",
            {
                "request": request,
                "error": "Этот снимок был одноразовым и уже самоуничтожен.",
                "t": t,
                "theme": theme,
            },
            status_code=410,
        )

    # Check PIN protection
    pin_required = False
    pin_error = None
    if drop.pin_code_hash:
        if not pin:
            pin_required = True
        else:
            hashed_input = hashlib.sha256(pin.strip().encode("utf-8")).hexdigest()
            if hashed_input != drop.pin_code_hash:
                pin_required = True
                pin_error = "Неверный PIN-код доступа."

    if pin_required:
        return templates.TemplateResponse(
            "media_showcase_item.html",
            {
                "request": request,
                "drop": drop,
                "pin_required": True,
                "pin_error": pin_error,
                "token": token,
                "t": t,
                "theme": theme,
            },
        )

    # Increment view counter
    drop.view_count += 1
    if drop.exposure_type == "one_time":
        drop.is_burned = True
    await db.flush()

    return templates.TemplateResponse(
        "media_showcase_item.html",
        {
            "request": request,
            "drop": drop,
            "token": token,
            "media_path": drop.media_path,
            "is_permanent": drop.is_permanent_immutable,
            "expires_at": drop.expires_at,
            "view_count": drop.view_count,
            "t": t,
            "theme": theme,
        },
    )
