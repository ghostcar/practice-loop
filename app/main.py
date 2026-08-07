import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.dashboard import router as dashboard_router
from app.api.entities import router as entities_router
from app.api.import_data import router as import_router
from app.api.llm_configs import router as llm_configs_router
from app.api.points_v2 import router as points_v2_router
from app.api.tasks import router as tasks_router
from app.api.training import router as training_router
from app.auth import get_optional_user
from app.config import settings
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.telegram.bot import setup_webhook, start_polling, stop_polling, tg_router
from app.templates_setup import templates
from app.training.scheduler import start_auto_analysis, stop_auto_analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables if not exist, disable Jinja2 cache (dev mode)."""
    from app.database import engine
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Disable Jinja2 caching to avoid unhashable dict errors with i18n
    from app.templates_setup import templates

    templates.env.cache = None

    # Telegram: webhook (production) or polling (local dev)
    if getattr(settings, "tg_polling", False):
        await start_polling()
    else:
        base_url = getattr(settings, "tg_webhook_base_url", "https://localhost:8443")
        await setup_webhook(base_url)

    # Start auto-analysis scheduler
    await start_auto_analysis()

    yield

    # Shutdown: stop polling + auto-analysis
    await stop_polling()
    await stop_auto_analysis()


app = FastAPI(title="Practice Loop", version="0.5.0", lifespan=lifespan)


# --- Mount static files ---
with contextlib.suppress(RuntimeError):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")


# --- Health check ---


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# --- Home page ---


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_optional_user(request)
    locale = detect_locale(request, user.locale if user else None)
    theme = detect_theme(user.theme if user else None)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
        },
    )


# --- Include routers ---
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(entities_router)
app.include_router(llm_configs_router)
app.include_router(tasks_router)
app.include_router(training_router)
app.include_router(dashboard_router)
app.include_router(points_v2_router)
app.include_router(import_router)
app.include_router(calendar_router)
app.include_router(tg_router)
