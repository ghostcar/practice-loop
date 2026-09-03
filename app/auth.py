import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _load_prefs_context(user: User) -> None:
    """Populate the request-scoped prefs ContextVar (Step 9e).

    Runs in the auth dependencies (which every authenticated page uses) so
    templates read customization/discretion state via the sync context
    processor without per-page handler changes. The legacy ``theme`` column
    seeds ``theme_choice`` for existing users.
    """
    from app.prefs import prefs_from_dict, raw_dict, set_prefs

    raw = raw_dict(user.prefs)
    if "theme_choice" not in raw:
        raw["theme_choice"] = user.theme or "dark"
    set_prefs(prefs_from_dict(raw))


# --- Password helpers ---


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT helpers ---


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        # token_type distinguishes access JWTs from any future JWT token kind.
        # Legacy tokens (issued before M4) carry no "type" and are treated as access.
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
        # Reject JWTs minted for a different purpose (e.g. a refresh JWT).
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            return None
        return uuid.UUID(user_id)
    except (JWTError, ValueError):
        return None


# --- Refresh token helpers (M4 Mobile Foundation) ---


def generate_refresh_token() -> str:
    """Return a cryptographically random opaque refresh token (raw value).

    Only its SHA-256 hash is persisted (see app.api.tokens).
    """
    import secrets

    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest of a raw refresh token (constant-time-safe lookup key)."""
    import hashlib

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --- Auth dependency ---


async def _user_from_refresh_cookie(request: Request, db: AsyncSession) -> User | None:
    """Rotate a valid browser refresh cookie and return its user.

    The replacement access token is attached to the response by middleware;
    dependency resolution itself cannot mutate the eventual response safely,
    so this helper only provides the validated user. Expired access cookies are
    refreshed by the request middleware.
    """
    raw = request.cookies.get("refresh_token")
    if not raw:
        return None
    from app.models.api_token import ApiToken
    from app.timeutils import as_utc

    record = (
        await db.execute(select(ApiToken).where(ApiToken.token_hash == hash_refresh_token(raw)))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if record is None or record.revoked_at is not None or as_utc(record.expires_at) <= now:
        return None
    user = (
        await db.execute(select(User).where(User.id == record.user_id, User.disabled_at.is_(None)))
    ).scalar_one_or_none()
    if user is None:
        return None
    request.state.refreshed_access_token = create_access_token(user.id)
    record.revoked_at = now
    record.last_used_at = now
    replacement = generate_refresh_token()
    record2 = ApiToken(
        user_id=user.id,
        token_hash=hash_refresh_token(replacement),
        platform="web",
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        rotated_from_id=record.id,
    )
    db.add(record2)
    request.state.refreshed_refresh_token = replacement
    await db.flush()
    return user


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract user from JWT (header or cookie). Returns User or raises 401."""
    if token is None:
        token = request.cookies.get("access_token")
        if token is None:
            refreshed = await _user_from_refresh_cookie(request, db)
            if refreshed is not None:
                _load_prefs_context(refreshed)
                return refreshed
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

    user_id = decode_access_token(token)
    if user_id is None:
        refreshed = await _user_from_refresh_cookie(request, db)
        if refreshed is not None:
            _load_prefs_context(refreshed)
            raise HTTPException(status_code=401, detail="Access token refreshed; retry request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.id == user_id, User.disabled_at.is_(None)))
    user = result.scalar_one_or_none()
    if user is None or user.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    _load_prefs_context(user)
    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Dependency: require admin role. Raises 403 if not admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_optional_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Dependency: extract user or return None (no 401).

    Safe to call both via FastAPI DI and directly (e.g. the `/` home page,
    which has no DB session): when `token`/`db` are still Depends sentinels
    rather than resolved values, the cookie is used and a throwaway session
    is opened for the lookup.
    """
    # When called directly (not via FastAPI DI), token may be a Depends object
    if token is not None and not isinstance(token, str):
        token = None
    if token is None:
        token = request.cookies.get("access_token")
    if token is None:
        return None

    user_id = decode_access_token(token)
    if user_id is None:
        return None

    if not isinstance(db, AsyncSession):
        # Direct call without DI: open a throwaway session for the lookup.
        from app.database import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id, User.disabled_at.is_(None)))
            user = result.scalar_one_or_none()
            if user is not None:
                _load_prefs_context(user)
            return user

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        _load_prefs_context(user)
    return user
