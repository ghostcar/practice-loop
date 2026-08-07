"""Security: CSRF protection, object-level ownership checks, idempotency guards."""

import hashlib
import hmac
import secrets
import uuid

from fastapi import HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
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
        secure=False,  # Allow HTTP in dev; set True in production
        max_age=86400,
    )
    return raw


def verify_csrf(request: Request) -> None:
    """Verify the CSRF token from header or form field against the cookie."""
    if request.method in CSRF_SAFE_METHODS:
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")

    # Check header (HTMX auto-includes X-CSRF-Token from meta tag)
    header_token = request.headers.get(CSRF_HEADER_NAME)

    if header_token and not hmac.compare_digest(header_token, cookie_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch")


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

    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id)
    )
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
    """Idempotent task completion: only processes if status allows it."""
    if log.status == "completed":
        return {"status": "already_completed", "idempotent": True}
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    log.status = "completed"
    db.add(log)
    await db.flush()
    result = await on_complete_fn(db, user.id, log)
    result["idempotent"] = False
    return result


async def interrupt_once(
    db: AsyncSession,
    log,
    user: User,
    on_interrupt_fn,
) -> dict:
    """Idempotent task interruption: only processes if status allows it."""
    if log.status in ("interrupted", "completed"):
        return {"status": f"already_{log.status}", "idempotent": True}
    if log.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    log.status = "interrupted"
    db.add(log)
    await db.flush()
    result = await on_interrupt_fn(db, user.id, log)
    result["idempotent"] = False
    return result
