from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class ApiToken(Base):
    """Opaque refresh token issued by the JSON auth API (Mobile Foundation, M4).

    Only the SHA-256 hash of the token is stored — the raw value is returned to
    the client once and never persisted, so a DB leak does not expose usable
    refresh tokens. Tokens are revocable and rotated on every ``/refresh``.
    """

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex digest of the raw refresh token (64 chars).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(30), nullable=True)  # ios / android / web / other
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Audit chain: id of the token this one replaced (rotation). Plain UUID,
    # no FK, to avoid cascade cycles on user deletion.
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ApiToken(user={self.user_id}, platform={self.platform})>"
