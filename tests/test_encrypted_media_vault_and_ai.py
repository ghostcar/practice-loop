"""Integration tests for Encrypted Media Vault, AI Comparison, Watermarking, and Auto-Tagging."""

import io

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.media_comparison import compare_before_after_photos
from app.agent.media_tagging import auto_tag_and_catalog_media
from app.media.crypto import decrypt_media_bytes, encrypt_media_bytes, generate_vault_encryption_key
from app.media.watermark import apply_security_watermark
from app.models.media import MediaAsset
from app.models.user import User


def test_aes_256_gcm_encryption_decryption_cycle():
    """Verify AES-256-GCM encryption and decryption at rest."""
    key = generate_vault_encryption_key()
    assert len(key) == 32

    original_payload = b"SECRET_PROOF_IMAGE_BINARY_DATA_12345"
    encrypted = encrypt_media_bytes(original_payload, key)
    assert encrypted != original_payload
    assert len(encrypted) > len(original_payload)

    decrypted = decrypt_media_bytes(encrypted, key)
    assert decrypted == original_payload


def test_apply_security_watermark_to_image():
    """Verify watermarking engine applies text overlay onto image bytes."""
    img = Image.new("RGB", (200, 200), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    watermarked_bytes = apply_security_watermark(raw_bytes, watermark_text="PROTECTED | USER: test_user | 2026-08-20")
    assert watermarked_bytes is not None
    assert len(watermarked_bytes) > 0


@pytest.mark.asyncio
async def test_compare_before_after_photos_ai_analysis(db_session: AsyncSession, test_user: User):
    """Verify AI compares before and after progression photos."""
    res = await compare_before_after_photos(
        db_session, test_user, photo_before_path="/uploads/day1.jpg", photo_after_path="/uploads/day7.jpg"
    )
    assert res["status"] == "success"
    assert res["similarity_score"] >= 80.0
    assert "Отчет Сравнения Мультимодального ИИ" in res["summary_markdown"]


@pytest.mark.asyncio
async def test_auto_tag_and_catalog_media(db_session: AsyncSession, test_user: User):
    """Verify AI auto-tags media assets and assigns smart album categories."""
    asset = MediaAsset(
        owner_id=test_user.id,
        owner_type="lock_session",
        file_path="/uploads/lock_checkin.jpg",
        mime_type="image/jpeg",
    )
    db_session.add(asset)
    await db_session.flush()

    tag_res = await auto_tag_and_catalog_media(db_session, str(asset.id))
    assert tag_res["status"] == "success"
    assert "chastity" in tag_res["tags"]
    assert tag_res["smart_album"] == "Альбом Чек-инов Ключника"
