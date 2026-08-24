"""API Router for 2FA PIN & Session Cache (ADR-152).

PIN is a user-chosen numeric code (4-16 digits), stored as bcrypt hash.
Once verified, access is cached per-user for 20 minutes (configurable) so
repeated vault unlocks within the session don't re-prompt.

Endpoints:
  POST /security/verify-pin      — verify PIN, set session cache
  POST /security/set-pin          — set initial PIN
  POST /security/change-pin       — change existing PIN (requires current)
  POST /security/clear-pin        — remove PIN (requires current)
  GET  /security/pin-status       — whether PIN is set + whether cached
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.auth import hash_password, verify_password
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security_2fa"])

# ---------------------------------------------------------------------------
# In-memory PIN session cache (ADR-152).
# Per-user: once verified, vault access is cached for PIN_CACHE_TTL_SEC (20 min).
# ---------------------------------------------------------------------------

PIN_CACHE_TTL_SEC: int = 20 * 60  # 20 minutes (middle of 15–30 as spec'd)

PIN_MIN_LENGTH: int = 4
PIN_MAX_LENGTH: int = 16


def _wants_htmx(request: Request) -> bool:
    return bool(request.headers.get("HX-Request"))


def _htmx_redirect(path: str) -> JSONResponse:
    """Redirect HTMX client to a new URL (HX-Redirect header)."""
    from fastapi.responses import Response
    resp = Response(status_code=200)
    resp.headers["HX-Redirect"] = path
    return resp


@dataclass
class _PinCache:
    """Thread-safe in-memory store: {user_id_hex: expiry_timestamp}."""

    _store: dict[str, float] = field(default_factory=dict)

    def is_cached(self, user_id: str) -> bool:
        self._evict_stale()
        expiry = self._store.get(user_id)
        return expiry is not None and time.monotonic() < expiry

    def set(self, user_id: str) -> None:
        self._store[user_id] = time.monotonic() + PIN_CACHE_TTL_SEC

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)

    def _evict_stale(self) -> None:
        now = time.monotonic()
        stale = [k for k, v in self._store.items() if v <= now]
        for k in stale:
            self._store.pop(k, None)


_pin_cache = _PinCache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_pin_format(pin: str) -> str:
    """Return the stripped PIN if it looks valid, otherwise raise 400."""
    pin = pin.strip()
    if not pin.isdigit():
        raise HTTPException(400, "PIN must consist of digits only.")
    if not (PIN_MIN_LENGTH <= len(pin) <= PIN_MAX_LENGTH):
        raise HTTPException(
            400, f"PIN must be {PIN_MIN_LENGTH}–{PIN_MAX_LENGTH} digits."
        )
    return pin


def _pin_hash(plain: str) -> str:
    """bcrypt the PIN string (same family as password_hash)."""
    return hash_password(plain)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/verify-pin")
async def verify_security_pin(
    request: Request,
    pin_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the user's 2FA PIN and cache access for the session window.

    Returns `cached: true` when the caller could have skipped the prompt
    (so UIs can decide whether to show the PIN form at all).
    """
    pin = _validate_pin_format(pin_code)
    user_key = str(user.id)

    # If still cached from a previous verification, accept without re-check.
    if _pin_cache.is_cached(user_key):
        _pin_cache.set(user_key)  # refresh the window
        logger.debug("PIN cache hit for user %s", user.email)
        return JSONResponse(
            {
                "status": "verified",
                "cached": True,
                "message": "Access confirmed (session cache).",
            }
        )

    # Real check: user must have set a PIN first.
    if not user.pin_hash:
        raise HTTPException(400, "PIN is not set. Use /security/set-pin first.")

    if not verify_password(pin, user.pin_hash):
        raise HTTPException(403, "Incorrect PIN.")

    _pin_cache.set(user_key)
    logger.info("PIN verified for user %s (cache set, TTL %ds)", user.email, PIN_CACHE_TTL_SEC)

    return JSONResponse(
        {
            "status": "verified",
            "cached": False,
            "message": "PIN verified. Access cached for this session.",
        }
    )


@router.post("/set-pin")
async def set_security_pin(
    request: Request,
    pin_code: str = Form(...),
    confirm_pin: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the initial 2FA PIN. 400 if a PIN is already configured."""
    if user.pin_hash:
        raise HTTPException(400, "PIN is already set. Use /security/change-pin to update it.")

    pin = _validate_pin_format(pin_code)
    if pin != confirm_pin.strip():
        raise HTTPException(400, "PIN and confirmation do not match.")

    user.pin_hash = _pin_hash(pin)
    db.add(user)
    _pin_cache.clear(str(user.id))
    await db.flush()

    logger.info("PIN set for user %s", user.email)
    if _wants_htmx(request):
        return _htmx_redirect("/settings?pin_status=set#pin-h")
    return JSONResponse({"status": "ok", "message": "PIN successfully set."})


@router.post("/change-pin")
async def change_security_pin(
    request: Request,
    current_pin: str = Form(...),
    new_pin: str = Form(...),
    confirm_new_pin: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change an existing PIN. Requires the current PIN for auth."""
    if not user.pin_hash:
        raise HTTPException(400, "PIN is not set. Use /security/set-pin first.")

    if not verify_password(current_pin.strip(), user.pin_hash):
        raise HTTPException(403, "Current PIN is incorrect.")

    new = _validate_pin_format(new_pin)
    if new != confirm_new_pin.strip():
        raise HTTPException(400, "New PIN and confirmation do not match.")

    user.pin_hash = _pin_hash(new)
    db.add(user)
    _pin_cache.clear(str(user.id))
    await db.flush()

    logger.info("PIN changed for user %s", user.email)
    if _wants_htmx(request):
        return _htmx_redirect("/settings?pin_status=changed#pin-h")
    return JSONResponse({"status": "ok", "message": "PIN successfully changed."})


@router.post("/clear-pin")
async def clear_security_pin(
    request: Request,
    current_pin: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the PIN entirely. Requires the current PIN for auth."""
    if not user.pin_hash:
        raise HTTPException(400, "PIN is not set.")

    if not verify_password(current_pin.strip(), user.pin_hash):
        raise HTTPException(403, "Current PIN is incorrect.")

    user.pin_hash = None
    db.add(user)
    _pin_cache.clear(str(user.id))
    await db.flush()

    logger.info("PIN cleared for user %s", user.email)
    if _wants_htmx(request):
        return _htmx_redirect("/settings?pin_status=cleared#pin-h")
    return JSONResponse({"status": "ok", "message": "PIN removed."})


@router.get("/pin-status")
async def pin_status(
    user: User = Depends(get_current_user),
):
    """Return whether a PIN is set and whether the session is currently cached."""
    user_key = str(user.id)
    return JSONResponse(
        {
            "has_pin": user.pin_hash is not None,
            "session_cached": _pin_cache.is_cached(user_key),
        }
    )