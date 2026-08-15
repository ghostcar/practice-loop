from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.i18n import get_supported_locales, get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.security import set_csrf_cookie
from app.templates_setup import templates

router = APIRouter()


# --- Pages ---


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration form page."""
    locale = detect_locale(request)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "request": request,
            "t": t,
            "locale": locale,
            "error": None,
            "success": None,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login form page."""
    locale = detect_locale(request)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "t": t,
            "locale": locale,
            "error": None,
        },
    )


# --- API: Register ---


@router.post("/auth/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(min_length=6, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    locale = detect_locale(request)
    t = get_translations(locale)

    # Check if user already exists
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    existing = result.scalar_one_or_none()

    if existing is not None:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "t": t,
                "locale": locale,
                "error": t["error_user_exists"],
                "success": None,
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    # Create user
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        locale=locale,
        theme="dark",
    )
    db.add(user)
    await db.flush()

    # Redirect to login with success message
    response = RedirectResponse(url="/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)
    return response


# --- API: Login ---


@router.post("/auth/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and set JWT cookie, then redirect."""
    locale = detect_locale(request)
    t = get_translations(locale)

    # Find user
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "t": t,
                "locale": locale,
                "error": t["error_invalid_credentials"],
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Create JWT and redirect to dashboard
    from app.config import settings

    token = create_access_token(user.id)
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    # Secure is meaningful only over HTTPS. On plain-http loopback (local dev,
    # browser E2E) strict engines (WebKit) drop a Secure cookie entirely; the
    # flag there is both useless and harmful. Real deployments (non-loopback)
    # keep Secure in production.
    loopback = request.url.hostname in ("127.0.0.1", "localhost", "::1")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.app_env == "production" and not loopback,
        samesite="lax",
        max_age=86400,  # 24 hours
        path="/",
    )
    set_csrf_cookie(response, request)
    return response


# --- API: Logout (POST only — audit: GET logout is a CSRF/logout vector) ---


@router.post("/auth/logout")
async def logout():
    """Clear auth cookie and redirect to home. POST only."""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("csrf_token", path="/")
    return response


# --- API: Locale toggle ---


@router.post("/settings/locale")
async def set_locale(
    request: Request,
    locale: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user locale preference."""
    if locale not in get_supported_locales():
        locale = "en"

    user.locale = locale
    db.add(user)

    # Redirect back
    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# --- API: Theme toggle ---


@router.post("/settings/theme")
async def set_theme(
    request: Request,
    theme: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user theme preference (dark/light/system, Step 9e)."""
    if theme not in ("dark", "light", "system"):
        theme = "dark"

    user.theme = theme
    # keep the raw choice in prefs so the shell can re-resolve 'system' on the client
    from app.prefs import raw_dict, sanitize_prefs

    raw = sanitize_prefs(raw_dict(user.prefs))
    raw["theme_choice"] = theme
    user.prefs = raw
    db.add(user)

    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
