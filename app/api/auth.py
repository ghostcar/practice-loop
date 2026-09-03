from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    generate_refresh_token,
    get_current_user,
    get_optional_user,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.database import get_db
from app.i18n import get_supported_locales, get_translations
from app.i18n.helpers import detect_locale
from app.models.api_token import ApiToken
from app.models.user import User
from app.security import set_csrf_cookie
from app.templates_setup import templates

router = APIRouter()


# --- Pages ---


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: User | None = Depends(get_optional_user)):
    """Serve the registration form page."""
    # Authed users don't belong on the auth pages. The forms carry no
    # csrf_token, and CSRF is enforced for authenticated sessions — a second
    # registration/login attempt would 403 (seen in browser E2E). Redirecting
    # authed visitors keeps the flow clean and the quirk unreachable.
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

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
async def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    """Serve the login form page."""
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

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
    user: User | None = Depends(get_optional_user),
):
    """Register a new user account."""
    # Guard: an authenticated session must not silently create another account
    # (nor hit the CSRF 403 — the register form carries no token).
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

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

    # Auto-login and redirect to onboarding wizard for new users.
    token = create_access_token(user.id)

    # Mark onboarding as not completed
    from app.prefs import sanitize_prefs

    raw = sanitize_prefs(user.prefs)
    raw["onboarding_completed"] = False
    user.prefs = raw
    db.add(user)
    await db.flush()

    response = RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)
    from app.config import settings

    raw_refresh = generate_refresh_token()
    db.add(
        ApiToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            platform="web",
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.flush()
    loopback = request.url.hostname in ("127.0.0.1", "localhost", "::1")

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.app_env == "production" and not loopback,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.app_env == "production" and not loopback,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/auth",
    )
    from app.security import set_csrf_cookie

    set_csrf_cookie(response, request)
    return response


# --- API: Login ---


@router.post("/auth/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Authenticate user and set JWT cookie, then redirect."""
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    locale = detect_locale(request)
    t = get_translations(locale)

    # Find user
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if user is None or user.disabled_at is not None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "t": t,
                "locale": locale,
                "error": t["error_invalid_credentials"],
                "email": email.strip(),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # First login (and newly enabled modules) goes through one-time consent.
    from app.config import settings
    from app.consent import missing_consents
    from app.prefs import sanitize_prefs

    module_keys = [f"module:{name}" for name in sanitize_prefs(user.prefs)["enabled_modules"]]
    missing = await missing_consents(db, user.id, module_keys)

    token = create_access_token(user.id)
    raw_refresh = generate_refresh_token()
    db.add(
        ApiToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            platform="web",
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.flush()
    target = "/consent/setup?required=" + ",".join(missing) if missing else "/dashboard"
    # Only relative local paths may be used as a post-login destination.
    target = target if target.startswith("/") and not target.startswith("//") else "/dashboard"
    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="last_login_email",
        value=user.email,
        max_age=365 * 24 * 60 * 60,
        httponly=False,
        secure=settings.app_env == "production" and request.url.hostname not in ("127.0.0.1", "localhost", "::1"),
        samesite="lax",
        path="/login",
    )
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
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.app_env == "production" and not loopback,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/auth",
    )
    set_csrf_cookie(response, request)
    return response


# --- API: Logout (POST only — audit: GET logout is a CSRF/logout vector) ---


@router.post("/auth/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the session's refresh token, clear auth cookies, redirect home.

    POST only (audit: GET logout is a CSRF/logout vector). Revocation closes
    the audit finding: a refresh cookie captured before logout must no longer
    mint new access tokens (the middleware rotation path checks revoked_at).
    """
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        from app.models.api_token import ApiToken

        record = (
            await db.execute(select(ApiToken).where(ApiToken.token_hash == hash_refresh_token(raw_refresh)))
        ).scalar_one_or_none()
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            await db.flush()

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth")
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
