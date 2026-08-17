"""Practice Loop — FastAPI application shell with product composition (C0).

Routes, navigation and background jobs are registered via immutable
ProductComposition built once at import time (validated from env vars).
Three variants supported: tracker, timer, combined — all from one codebase
and one Alembic head.
"""

from __future__ import annotations

import contextlib
import logging
import mimetypes
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
from app.version import __version__

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

    # Reminder engine — medication/care/timer reminders (ADR-095, relief-only).
    from app.reminders.scheduler import start_reminders

    await start_reminders()

    yield

    # Shutdown.
    from app.reminders.scheduler import stop_reminders

    await stop_reminders()
    if _tg_polling and settings.tg_bot_token:
        from app.telegram.bot import stop_polling as tg_stop

        await tg_stop()
    if composition.tracker_active:
        from app.training.scheduler import stop_auto_analysis

        await stop_auto_analysis()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Practice Loop", version=__version__, lifespan=lifespan)


# ---------------------------------------------------------------------------
# CSRF middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if (
        request.url.path.startswith("/static")
        or request.url.path == "/healthz"
        or request.url.path.startswith("/api/v2/platform")  # readonly discovery
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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add baseline security headers to every response (audit P1-6).

    HSTS, nosniff, Referrer-Policy, X-Frame-Options and Permissions-Policy are
    safe to send on all responses. CSP is report-only for now: templates still
    contain inline <script>/handlers and runtime Tailwind, so an enforcing CSP
    would break the UI (Gate C — collect first, then enforce).
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault(
        "Content-Security-Policy-Report-Only",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'",
    )
    return response


@app.middleware("http")
async def client_tz_middleware(request: Request, call_next):
    """Propagate the client timezone into a request-scoped ContextVar.

    The IANA name comes from the ``client_tz`` cookie (written by app.js via
    ``Intl``). Day-boundary helpers (``timeutils.local_today``) read this so
    "today" reflects the device's local calendar day, not UTC.
    """
    from app.timeutils import reset_client_tz, set_client_tz

    token = set_client_tz(request.cookies.get("client_tz"))
    try:
        return await call_next(request)
    finally:
        reset_client_tz(token)


# ---------------------------------------------------------------------------
# Static files & health
# ---------------------------------------------------------------------------

# Self-hosted fonts (Step 9a): Python's mimetypes (3.11 container) does not know
# .woff2/.woff → Starlette would serve them as text/plain and Firefox/WebKit
# reject the download (console error, fallback fonts). Register the types so
# StaticFiles returns the correct Content-Type.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")

with contextlib.suppress(RuntimeError):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Private uploads are no longer mounted publicly (audit P0-1): they are served
# through the authorized, owner-scoped `GET /uploads/{path}` route in app.api.uploads.


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
        # Audit P2-3: never leak exception internals (hostname, DB name, etc.)
        # to the client — log details server-side only.
        from fastapi.responses import PlainTextResponse

        logger.warning("Readiness check failed", exc_info=exc)
        return PlainTextResponse("not ready", status_code=503)
    return "ready"


# ---------------------------------------------------------------------------
# Platform routes (always registered)
# ---------------------------------------------------------------------------

from app.platform.capabilities import router as capabilities_router  # noqa: E402

app.include_router(capabilities_router)

# Universal media + verification (platform-level, always available)
from app.api.media import router as media_router  # noqa: E402
from app.api.uploads import router as uploads_router  # noqa: E402
from app.api.verification import router as verification_router  # noqa: E402

app.include_router(media_router)
app.include_router(uploads_router)
app.include_router(verification_router)

from app.api.auth import router as auth_router  # noqa: E402
from app.api.push import router as push_router  # noqa: E402
from app.api.settings import router as settings_router  # noqa: E402
from app.api.tokens import router as tokens_router  # noqa: E402

app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(push_router)
app.include_router(tokens_router)

from app.telegram.bot import tg_router  # noqa: E402

app.include_router(tg_router)

# ---------------------------------------------------------------------------
# Tracker routes
# ---------------------------------------------------------------------------

if composition.tracker_active:
    from app.api.admin import router as admin_router  # noqa: E402
    from app.api.attachments import router as attachments_router  # noqa: E402
    from app.api.calendar import router as calendar_router  # noqa: E402
    from app.api.care import json_router as care_json_router  # noqa: E402
    from app.api.care import router as care_router  # noqa: E402
    from app.api.catalog import json_router as catalog_json_router  # noqa: E402
    from app.api.catalog import router as catalog_router  # noqa: E402
    from app.api.dashboard import router as dashboard_router  # noqa: E402
    from app.api.diets import router as diets_router  # noqa: E402
    from app.api.entities import router as entities_router  # noqa: E402
    from app.api.health import json_router as health_json_router  # noqa: E402
    from app.api.health import router as health_router  # noqa: E402
    from app.api.import_data import router as import_router  # noqa: E402
    from app.api.insights import json_router as insights_json_router  # noqa: E402
    from app.api.insights import router as insights_router  # noqa: E402
    from app.api.journal import json_router as journal_json_router  # noqa: E402
    from app.api.journal import router as journal_router  # noqa: E402
    from app.api.knowledge import router as knowledge_router  # noqa: E402
    from app.api.llm_configs import router as llm_configs_router  # noqa: E402
    from app.api.media_vault import router as media_vault_router  # noqa: E402
    from app.api.media_verify import json_router as media_verify_json_router  # noqa: E402
    from app.api.media_verify import page_router as media_verify_page_router  # noqa: E402
    from app.api.medication import json_router as medication_json_router  # noqa: E402
    from app.api.medication import router as medication_router  # noqa: E402
    from app.api.points import router as points_router  # noqa: E402
    from app.api.prompt_templates import json_router as prompt_templates_json_router  # noqa: E402
    from app.api.prompt_templates import page_router as prompt_templates_page_router  # noqa: E402
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
        points_router,
        task_flows_router,
        references_router,
        import_router,
        calendar_router,
        attachments_router,
        diets_router,
        prompt_templates_page_router,
        prompt_templates_json_router,
        media_verify_page_router,
        media_verify_json_router,
        media_vault_router,
        knowledge_router,
    ):
        app.include_router(_router)

    if composition.medication_enabled:
        app.include_router(medication_router)
        app.include_router(medication_json_router)

    if composition.health_enabled:
        app.include_router(health_router)
        app.include_router(health_json_router)

    if composition.journal_enabled:
        app.include_router(journal_router)
        app.include_router(journal_json_router)

    if composition.care_enabled:
        app.include_router(care_router)
        app.include_router(care_json_router)

    if composition.catalog_enabled:
        app.include_router(catalog_router)

    if composition.insights_enabled:
        app.include_router(insights_router)
        app.include_router(insights_json_router)
        app.include_router(catalog_json_router)

    if composition.aftercare_enabled:
        from app.api.aftercare import json_router as aftercare_json_router  # noqa: E402
        from app.api.aftercare import router as aftercare_router  # noqa: E402

        app.include_router(aftercare_router)
        app.include_router(aftercare_json_router)

    if composition.consent_enabled:
        from app.api.consent import json_router as consent_json_router  # noqa: E402
        from app.api.consent import router as consent_router  # noqa: E402

        app.include_router(consent_router)
        app.include_router(consent_json_router)

# ---------------------------------------------------------------------------
# Timer routes (C1-C8 — registered when LOCKTIMER_CORE_ENABLED)
# ---------------------------------------------------------------------------

if composition.timer_operational:
    from app.api.chastity_checkins import json_router as chastity_json_router  # noqa: E402
    from app.api.chastity_checkins import router as chastity_router  # noqa: E402
    from app.api.device_events import json_router as device_events_json_router  # noqa: E402
    from app.api.device_events import router as device_events_router  # noqa: E402
    from app.api.locktimer_commands import router as locktimer_commands_router  # noqa: E402
    from app.api.locktimer_proposals import router as locktimer_proposals_router  # noqa: E402
    from app.api.locktimer_ui import router as locktimer_ui_router  # noqa: E402

    app.include_router(locktimer_commands_router)
    app.include_router(locktimer_proposals_router)
    app.include_router(locktimer_ui_router)
    app.include_router(device_events_router)
    app.include_router(device_events_json_router)
    app.include_router(chastity_router)
    app.include_router(chastity_json_router)

# ---------------------------------------------------------------------------
# Register domain social adapters (S1 — after route registration)
# ---------------------------------------------------------------------------

if composition.social_operational and composition.social_tracker_adapter_enabled:
    from app.platform.social import register_adapter
    from app.platform.social.adapters import TrackerSocialAdapter

    register_adapter(TrackerSocialAdapter())
    logger.info("Social Tracker adapter registered")

if composition.social_operational and composition.social_timer_adapter_enabled:
    from app.platform.social import register_adapter
    from app.platform.social.adapters import TimerSocialAdapter

    register_adapter(TimerSocialAdapter())
    logger.info("Social Timer adapter registered")

# ---------------------------------------------------------------------------
# Platform Social routes (S0+ — registered when SOCIAL_ENABLED)
# ---------------------------------------------------------------------------

if composition.social_operational:
    from app.platform.social.api import router as social_router  # noqa: E402

    app.include_router(social_router)
    logger.info("Platform Social enabled")

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
