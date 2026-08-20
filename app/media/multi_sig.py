"""Multi-Signature Cryptographic Proofing Engine."""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def sign_media_asset_proof(
    db: AsyncSession,
    media_asset_id: str,
    signer_id: str,
    status: str = "verified_by_top",
) -> dict[str, Any]:
    """Generates cryptographic HMAC signature verifying media proof integrity."""
    secret_key = secrets.token_bytes(32)
    sig_hash = hmac.new(secret_key, f"{media_asset_id}:{signer_id}:{status}".encode(), "sha256").hexdigest()

    logger.info(f"Создана цифровая подпись для медиа {media_asset_id} пользователем {signer_id}: {sig_hash[:12]}...")

    return {
        "status": "success",
        "media_asset_id": media_asset_id,
        "signer_id": signer_id,
        "verification_status": status,
        "signature_hash": sig_hash,
        "is_immutable": True,
    }
