"""Integration tests for Video Frames, Anti-Spoofing pHash, Media Timeline UI, and Multi-Sig Proofing."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.anti_spoofing import audit_image_authenticity, calculate_perceptual_hash
from app.media.multi_sig import sign_media_asset_proof
from app.media.video_frames import extract_video_key_frames
from app.models.media import MediaAsset
from app.models.user import User


def test_extract_video_key_frames():
    """Verify video key frame extraction returns expected image byte frames."""
    dummy_video_bytes = b"HEADER_VIDEO_BYTES_STREAM_12345"
    frames = extract_video_key_frames(dummy_video_bytes, frame_count=3)
    assert len(frames) == 3
    assert all(isinstance(f, bytes) and len(f) > 0 for f in frames)


def test_calculate_perceptual_hash_and_exif_audit():
    """Verify dHash calculation and EXIF authenticity audit."""
    dummy_image_bytes = b"BINARY_IMAGE_DATA_54321"
    phash = calculate_perceptual_hash(dummy_image_bytes)
    assert isinstance(phash, str)
    assert len(phash) >= 8

    audit = audit_image_authenticity(dummy_image_bytes)
    assert audit["status"] == "success"
    assert audit["authenticity_score"] >= 90.0


@pytest.mark.asyncio
async def test_media_timeline_page_rendering(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """GET /media/timeline returns 200 OK and renders chronological media list."""
    asset = MediaAsset(owner_id=test_user.id, owner_type="activity_log", file_path="/uploads/proof.jpg")
    db_session.add(asset)
    await db_session.commit()

    resp = await auth_client.get("/media/timeline")
    assert resp.status_code == 200
    assert "Хронологическая Лента Медиа" in resp.text


@pytest.mark.asyncio
async def test_sign_media_asset_proof_multi_sig(db_session: AsyncSession, test_user: User):
    """Verify multi-signature cryptographic proof signing."""
    res = await sign_media_asset_proof(
        db_session, media_asset_id="asset_123", signer_id=str(test_user.id), status="verified_by_top"
    )
    assert res["status"] == "success"
    assert len(res["signature_hash"]) == 64
    assert res["is_immutable"] is True
