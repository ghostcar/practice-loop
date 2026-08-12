"""Practice Loop — FastAPI application shell with product composition (C0).

Routes, navigation and background jobs are registered via immutable
ProductComposition built once at import time (validated from env vars).
Three variants supported: tracker, timer, combined — all from one codebase
and one Alembic head.
"""

from __future__ import annotations

import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import app.platform.composition as _comp
from app.auth import get_optional_user
from app.config import settings
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.platform.composition import build_product_composition
from app.security import ensure_csrf_cookie, verify_csrf
from app.templates_setup import templates

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build composition at import time so route registration sees it.
# Must write through the module-level singleton (used by templates_setup.py).
# ---------------------------------------------------------------------------

_comp.composition = build_product_composition()
composition = _comp.composition


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start platform services conditionally."""

    # Disable Jinja2 cache (i18n dicts are unhashable).
    templates.env.cache = None

    # Telegram bot (platform service — available in all variants).
    _tg_polling = getattr(settings, "tg_polling", False)
    if _tg_polling and settings.tg_bot_token:
        from app.telegram.bot import start_polling as tg_start

        await tg_start()
    elif settings.tg_bot_token:
        from app.telegram.bot import setup_webhook as tg_webhook

        base_url = getattr(settings, "tg_webhook_base_url", "https://localhost:8443")
        await tg_webhook(base_url)

    # Auto-analysis scheduler — Tracker-only.
    if composition.tracker_active:
        from app.training.scheduler import start_auto_analysis

        await start_auto_analysis()

    # Timer background jobs (placeholder for C4 — materializer/outbox runner).
    if composition.timer_operational:
        logger.info("LockTimer Core enabled — worker entry point reserved for C4")

    yield

    # Shutdown.
    if _tg_polling and settings.tg_bot_token:
        from app.telegram.bot import stop_polling as tg_stop

        await tg_stop()
    if composition.tracker_active:
        from app.training.scheduler import stop_auto_analysis

        await stop_auto_analysis()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Practice Loop", version="0.9.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# CSRF middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if (
        request.url.path.startswith("/static")
        or request.url.path.startswith("/uploads")
        or request.url.path == "/healthz"
        or request.url.path.startswith("/api/v1/platform")  # readonly discovery
    ):
        return await call_next(request)
    try:
        await verify_csrf(request)
    except Exception as e:
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse

        if isinstance(e, HTTPException):
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        raise
    return await call_next(request)


# ---------------------------------------------------------------------------
# Static files & health
# ---------------------------------------------------------------------------

with contextlib.suppress(RuntimeError):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

with contextlib.suppress(RuntimeError):
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


@app.get("/healthz/readiness", response_class=PlainTextResponse)
async def readiness():
    """Readiness probe — checks DB connectivity."""
    from app.database import get_db

    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            return "ready"
    except Exception as exc:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(f"not ready: {exc}", status_code=503)
    return "ready"


# ---------------------------------------------------------------------------
# Platform routes (always registered)
# ---------------------------------------------------------------------------

from app.platform.capabilities import router as capabilities_router  # noqa: E402

app.include_router(capabilities_router)

# Universal media + verification (platform-level, always available)
from app.api.media import router as media_router  # noqa: E402
from app.api.verification import router as verification_router  # noqa: E402

app.include_router(media_router)
app.include_router(verification_router)

from app.api.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)

from app.telegram.bot import tg_router  # noqa: E402

app.include_router(tg_router)

# ---------------------------------------------------------------------------
# Tracker routes
# ---------------------------------------------------------------------------

if composition.tracker_active:
    from app.api.admin import router as admin_router  # noqa: E402
    from app.api.attachments import router as attachments_router  # noqa: E402
    from app.api.calendar import router as calendar_router  # noqa: E402
    from app.api.dashboard import router as dashboard_router  # noqa: E402
    from app.api.diets import router as diets_router  # noqa: E402
    from app.api.entities import router as entities_router  # noqa: E402
    from app.api.import_data import router as import_router  # noqa: E402
    from app.api.llm_configs import router as llm_configs_router  # noqa: E402
    from app.api.points_v2 import router as points_v2_router  # noqa: E402
    from app.api.references import router as references_router  # noqa: E402
    from app.api.task_flows import router as task_flows_router  # noqa: E402
    from app.api.tasks import router as tasks_router  # noqa: E402
    from app.api.training import router as training_router  # noqa: E402

    for _router in (
        admin_router,
        entities_router,
        llm_configs_router,
        tasks_router,
        training_router,
        dashboard_router,
        points_v2_router,
        task_flows_router,
        references_router,
        import_router,
        calendar_router,
        attachments_router,
        diets_router,
    ):
        app.include_router(_router)

# ---------------------------------------------------------------------------
# Timer routes (C1-C8 — registered when LOCKTIMER_CORE_ENABLED)
# ---------------------------------------------------------------------------

if composition.timer_operational:
    from app.api.locktimer_commands import router as locktimer_commands_router  # noqa: E402
    from app.api.locktimer_proposals import router as locktimer_proposals_router  # noqa: E402
    from app.api.locktimer_ui import router as locktimer_ui_router  # noqa: E402

    app.include_router(locktimer_commands_router)
    app.include_router(locktimer_proposals_router)
    app.include_router(locktimer_ui_router)

# ---------------------------------------------------------------------------
# Root page — adapts to variant
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_optional_user(request)
    locale = detect_locale(request, user.locale if user else None)
    theme = detect_theme(user.theme if user else None)
    t = get_translations(locale)

    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "composition": composition,
        },
    )
    ensure_csrf_cookie(request, response)
    return response
