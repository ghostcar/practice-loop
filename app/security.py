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


def set_csrf_cookie(response: Response, request: Request | None = None) -> str:
    """Generate a CSRF token and set it as a cookie. Returns the raw token.

    Secure is meaningful only over HTTPS. On plain-http loopback (local dev,
    browser E2E) strict engines (WebKit) drop a Secure cookie entirely, so the
    flag is omitted there — mirroring the access_token cookie in auth.py.
    """
    raw = _generate_csrf_token()
    loopback = bool(request is not None and request.url.hostname in ("127.0.0.1", "localhost", "::1"))
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=raw,
        httponly=False,  # JS must be able to read it for HTMX headers
        samesite="lax",
        secure=settings.app_env == "production" and not loopback,
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
    return set_csrf_cookie(response, request)


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

    Audit hardening: an atomic ``UPDATE ... WHERE status='planned'`` (instead
    of read-check-write) makes concurrent double-complete safe — the second
    caller sees zero affected rows and gets an idempotent result, so a reward
    is granted only once. Stopped/other-status tasks keep their status and
    never receive completion rewards.
    """
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.models.activity_log import ActivityLog
    from app.models.task_history import ActivityTaskHistory
    from app.models.task_status import COMPLETED, PLANNED

    now = datetime.now(UTC)
    res = await db.execute(
        update(ActivityLog)
        .where(
            ActivityLog.id == log.id,
            ActivityLog.user_id == user.id,
            ActivityLog.status == PLANNED,
        )
        .values(status=COMPLETED, completed_at=now)
    )
    if res.rowcount == 0:
        await db.refresh(log)
        return {"status": f"already_{log.status}", "idempotent": True}

    log.status = COMPLETED
    log.completed_at = now
    db.add(
        ActivityTaskHistory(
            task_id=log.id,
            previous_status=PLANNED,
            new_status=COMPLETED,
            actor_id=user.id,
            parameter_snapshot=log.selected_params,
            comment=log.completion_comment,
        )
    )
    result = await on_complete_fn(db, user.id, log)
    result["idempotent"] = False
    return result


async def interrupt_once(
    db: AsyncSession,
    log,
    user: User,
    on_interrupt_fn,
) -> dict:
    """Atomically interrupt/stop a task exactly once.

    A task may be stopped while planned OR in progress (status machine:
    planned→stopped, in_progress→stopped). Once stopped it can never be
    stopped again or completed for a reward.
    """
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.models.activity_log import ActivityLog
    from app.models.task_history import ActivityTaskHistory
    from app.models.task_status import IN_PROGRESS, PLANNED, STOPPED

    # Capture previous status BEFORE the UPDATE (synchronize_session="evaluate"
    # mutates the in-session object as part of the UPDATE).
    previous = log.status
    res = await db.execute(
        update(ActivityLog)
        .where(
            ActivityLog.id == log.id,
            ActivityLog.user_id == user.id,
            ActivityLog.status.in_([PLANNED, IN_PROGRESS]),
        )
        .values(status=STOPPED)
    )
    if res.rowcount == 0:
        await db.refresh(log)
        return {"status": f"already_{log.status}", "idempotent": True}

    db.add(
        ActivityTaskHistory(
            task_id=log.id,
            previous_status=previous,
            new_status=STOPPED,
            actor_id=user.id,
            parameter_snapshot=log.selected_params,
        )
    )
    log.status = STOPPED
    result = await on_interrupt_fn(db, user.id, log)
    result["idempotent"] = False
    return result


async def transition_once(
    db: AsyncSession,
    log,
    user: User,
    to_status: str,
    comment: str | None = None,
    on_transition_fn=None,
) -> dict:
    """Atomically move a task to any legal status (ADR-040 status machine).

    Uses the same atomic ``UPDATE ... WHERE status=<current>`` pattern as
    complete_once/interrupt_once so concurrent transitions are safe. The
    transition is validated against STATUS_TRANSITIONS and recorded in
    ActivityTaskHistory. On ``completed`` the completed_at is stamped.
    """
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.models.activity_log import ActivityLog
    from app.models.task_history import ActivityTaskHistory
    from app.models.task_status import COMPLETED, can_transition

    if not can_transition(log.status, to_status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal transition: {log.status} → {to_status}",
        )

    now = datetime.now(UTC)
    values: dict = {"status": to_status}
    if to_status == COMPLETED:
        values["completed_at"] = now

    # Capture the previous status BEFORE the UPDATE: with the default
    # synchronize_session="evaluate", the in-session object is mutated by
    # the UPDATE itself, so reading after would yield the new status.
    previous = log.status
    res = await db.execute(
        update(ActivityLog)
        .where(
            ActivityLog.id == log.id,
            ActivityLog.user_id == user.id,
            ActivityLog.status == previous,
        )
        .values(**values)
    )
    if res.rowcount == 0:
        await db.refresh(log)
        return {"status": f"already_{log.status}", "idempotent": True}

    log.status = to_status
    if to_status == COMPLETED:
        log.completed_at = now
    db.add(
        ActivityTaskHistory(
            task_id=log.id,
            previous_status=previous,
            new_status=to_status,
            changed_at=now,
            comment=comment,
            parameter_snapshot=log.selected_params,
            actor_id=user.id,
        )
    )
    result: dict = {"status": to_status, "idempotent": False}
    if on_transition_fn is not None:
        result.update(await on_transition_fn(db, user.id, log, previous, to_status))
    return result
