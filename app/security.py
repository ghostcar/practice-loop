"""Security: CSRF protection, object-level ownership checks, idempotency guards."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

# ── CSRF Protection ─────────────────────────────────────────────────

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _generate_csrf_token() -> str:
    return secrets.token_hex(32)


def _hmac_csrf(token: str) -> str:
    key = settings.jwt_secret_key.encode()[:32]
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def set_csrf_cookie(response: Response) -> str:
    """Generate a CSRF token and set it as a cookie. Returns the raw token."""
    raw = _generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=raw,
        httponly=False,  # JS must be able to read it for HTMX headers
        samesite="lax",
        secure=settings.app_env == "production",  # HTTPS-only in production
        max_age=86400,
    )
    return raw


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    """Set the CSRF cookie only when the request doesn't already carry one.

    Re-issuing a fresh token on every page render (as the dashboard used to do)
    desynchronizes the token embedded in the HTML from the cookie the browser
    sends on the next request, which breaks the first POST with 403. The token
    is set once at login (or first anonymous visit) and then left untouched.
    """
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if existing:
        return existing
    return set_csrf_cookie(response)


async def verify_csrf(request: Request) -> None:
    """Verify the CSRF token from header or form field against the cookie."""
    if request.method in CSRF_SAFE_METHODS:
        return

    # Only enforce CSRF when there's an authenticated session
    if not request.cookies.get("access_token"):
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")

    # 1) Header — HTMX auto-includes X-CSRF-Token from the meta tag
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if header_token and hmac.compare_digest(header_token, cookie_token):
        return

    # 2) Form field — native HTML forms send csrf_token as a hidden input.
    #    Only form content types are parsed; JSON/other bodies are rejected
    #    without buffering. Cache the raw body first (request.body() sets
    #    request._body, which BaseHTTPMiddleware replays downstream), then
    #    parse the form from it. A broad except is intentional: any body-read
    #    failure (ClientDisconnect, bad multipart) must fail closed as 403.
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
        try:
            await request.body()
            form = await request.form()
            form_token = form.get(CSRF_FORM_FIELD)
        except Exception:
            form_token = None
        if form_token is not None and hmac.compare_digest(str(form_token), cookie_token):
            return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")


# ── Object-level ownership ──────────────────────────────────────────


class OwnershipChecker:
    """Helper for checking that the current user owns a resource."""

    def __init__(self, model_class, owner_attr: str = "user_id"):
        self.model_class = model_class
        self.owner_attr = owner_attr

    async def require_owner(
        self,
        resource_id: uuid.UUID,
        user: User,
        db: AsyncSession,
    ) -> object:
        """Fetch resource by ID and verify user owns it. Returns the object or raises 404."""
        result = await db.execute(
            select(self.model_class).where(
                self.model_class.id == resource_id,
                getattr(self.model_class, self.owner_attr) == user.id,
            )
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return obj


# ── Entity ownership helper (uses owner_id, not user_id) ────────────


async def require_entity_owner(
    entity_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> object:
    """Fetch entity by ID and verify user is the owner. Raises 404 if not found/not owned."""
    from app.models.entity import Entity  # noqa: PLC0415 — avoid circular import

    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return entity


# ── Idempotency guards ──────────────────────────────────────────────


async def complete_once(
    db: AsyncSession,
    log,
    user: User,
    on_complete_fn,
) -> dict:
    """Atomically complete a task exactly once.

    Audit hardening: an atomic ``UPDATE ... WHERE status='pending'`` (instead
    of read-check-write) makes concurrent double-complete safe — the second
    caller sees zero affected rows and gets an idempotent result, so a reward
    is granted only once. Interrupted tasks keep their interrupted status and
    never receive completion rewards.
    """
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.models.activity_log import ActivityLog

    now = datetime.now(UTC)
    res = await db.execute(
        update(ActivityLog)
        .where(
            ActivityLog.id == log.id,
            ActivityLog.user_id == user.id,
            ActivityLog.status == "pending",
        )
        .values(status="completed", completed_at=now)
    )
    if res.rowcount == 0:
        await db.refresh(log)
        return {"status": f"already_{log.status}", "idempotent": True}

    log.status = "completed"
    log.completed_at = now
    result = await on_complete_fn(db, user.id, log)
    result["idempotent"] = False
    return result


async def interrupt_once(
    db: AsyncSession,
    log,
    user: User,
    on_interrupt_fn,
) -> dict:
    """Atomically interrupt a task exactly once."""
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.models.activity_log import ActivityLog

    res = await db.execute(
        update(ActivityLog)
        .where(
            ActivityLog.id == log.id,
            ActivityLog.user_id == user.id,
            ActivityLog.status == "pending",
        )
        .values(status="interrupted")
    )
    if res.rowcount == 0:
        await db.refresh(log)
        return {"status": f"already_{log.status}", "idempotent": True}

    log.status = "interrupted"
    result = await on_interrupt_fn(db, user.id, log)
    result["idempotent"] = False
    return result
