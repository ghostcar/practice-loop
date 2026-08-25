"""Tests for Media Showcase, Dynamic Timer, Permanent Drops, Privacy Redaction, and Dead Man's Switch."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.ocr_seals import extract_seal_tag_from_photo
from app.media.privacy_mask import apply_privacy_mask
from app.media.sanitizer import strip_exif_metadata
from app.models.dead_mans_switch import DeadMansSwitchRule
from app.models.media import MediaAsset
from app.models.media_exposure import MediaExposureDrop
from app.models.user import User
from app.services.dead_mans_switch import (
    evaluate_all_dead_mans_switches,
    record_activity_heartbeat,
)
from app.services.smart_albums import (
    batch_delete_assets,
    create_encrypted_zip_export,
    get_smart_albums,
)


@pytest.fixture
def sample_image_bytes():
    """Generates a valid 100x100 RGB JPEG image."""
    img = Image.new("RGB", (100, 100), color=(180, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. EXIF & Privacy Masking Unit Tests
# ---------------------------------------------------------------------------


def test_strip_exif_metadata(sample_image_bytes):
    sanitized, audit = strip_exif_metadata(sample_image_bytes, "image/jpeg")
    assert isinstance(sanitized, bytes)
    assert audit["is_exif_stripped"] is True
    assert audit["width"] == 100
    assert audit["height"] == 100
    assert audit["hmac_proof"] is not None


def test_apply_privacy_mask(sample_image_bytes):
    boxes = [
        {"x": 10, "y": 10, "w": 30, "h": 30, "mode": "blur"},
        {"x": 50, "y": 50, "w": 20, "h": 20, "mode": "blackout"},
        {"x": 80, "y": 80, "w": 15, "h": 15, "mode": "pixelate"},
    ]
    masked = apply_privacy_mask(sample_image_bytes, boxes)
    assert isinstance(masked, bytes)
    assert len(masked) > 0


def test_extract_seal_tag_from_photo(sample_image_bytes):
    """v0.9.1: OCR engine returns status=success even when tesseract is unavailable."""
    res = extract_seal_tag_from_photo(sample_image_bytes, expected_tag="TAG-9842")
    assert res["status"] == "success"
    # Without tesseract, no tags can be extracted from random sample bytes.
    # The engine no longer simulates matches — it reports low confidence.
    assert res["is_match"] is False
    assert res["low_confidence"] is True
    assert res["confidence"] < 0.75


# ---------------------------------------------------------------------------
# 2. Smart Albums & Batch Operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_albums_and_permanent_protection(db_session: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        email=f"media_user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
    )
    db_session.add(user)
    await db_session.flush()

    # Create media assets
    a1 = MediaAsset(
        owner_id=user.id,
        owner_type="activity_session",
        file_path="/uploads/media/session1.jpg",
        state="ready",
    )
    a2 = MediaAsset(
        owner_id=user.id,
        owner_type="chastity_seal",
        file_path="/uploads/media/seal1.jpg",
        state="ready",
    )
    a3 = MediaAsset(
        owner_id=user.id,
        owner_type="general",
        file_path="/uploads/media/perm1.jpg",
        state="ready",
    )
    db_session.add_all([a1, a2, a3])

    # Mark a3 as permanent immutable drop
    perm_drop = MediaExposureDrop(
        user_id=user.id,
        media_path=a3.file_path,
        token="perm-token-123",
        exposure_type="permanent_immutable",
        is_permanent_immutable=True,
    )
    db_session.add(perm_drop)
    await db_session.flush()

    albums = await get_smart_albums(db_session, user.id)
    assert len(albums["all"]) == 3
    assert len(albums["sessions"]) == 1
    assert len(albums["chastity_seals"]) == 1
    assert len(albums["permanent_showcase"]) == 1

    # Test ZIP export
    zip_bytes = await create_encrypted_zip_export(db_session, user.id)
    assert len(zip_bytes) > 0

    # Test Batch Delete with Permanent Protection
    res = await batch_delete_assets(db_session, user.id, [a1.id, a3.id])
    assert res["deleted_count"] == 1  # a1 deleted
    assert res["protected_permanent_count"] == 1  # a3 protected!
    assert str(a3.id) in res["protected_ids"]


# ---------------------------------------------------------------------------
# 3. Media Exposure API Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_exposure_drops_flow(db_session: AsyncSession, auth_client: AsyncClient):
    # 1. Create Dynamic Timer Drop
    resp = await auth_client.post(
        "/media/exposure/create",
        json={
            "media_path": "/uploads/media/dynamic.jpg",
            "exposure_type": "dynamic_timer",
            "initial_duration_minutes": 60,
            "title": "Chastity Countdown",
            "pin_code": "1234",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    token = data["token"]
    assert data["exposure_type"] == "dynamic_timer"
    assert data["is_permanent_immutable"] is False

    # 2. Adjust Timer (+30 min)
    adjust_resp = await auth_client.post(
        f"/media/exposure/{token}/adjust-timer",
        data={"delta_minutes": 30},
    )
    assert adjust_resp.status_code == 200
    assert adjust_resp.json()["delta_minutes"] == 30

    # 3. Create Permanent Drop
    perm_resp = await auth_client.post(
        "/media/exposure/create",
        json={
            "media_path": "/uploads/media/permanent.jpg",
            "exposure_type": "permanent_immutable",
            "title": "Permanent Pillar",
        },
    )
    assert perm_resp.status_code == 200
    perm_token = perm_resp.json()["token"]
    assert perm_resp.json()["is_permanent_immutable"] is True

    # 4. Try to revoke Permanent Drop (must fail with 403)
    revoke_resp = await auth_client.post(f"/media/exposure/{perm_token}/revoke")
    assert revoke_resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Dead Man's Switch Engine Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_mans_switch_engine(db_session: AsyncSession, auth_client: AsyncClient):
    user_stmt = select(User).limit(1)
    user = (await db_session.execute(user_stmt)).scalar_one()

    # 1. Record heartbeat for wear checkin
    hb_res = await record_activity_heartbeat(db_session, user.id, "wear_checkin")
    assert hb_res["status"] == "heartbeat_recorded"

    # 2. Configure a strict 1-hour DMS switch
    cfg_resp = await auth_client.post(
        "/api/v2/dms/configure",
        json={
            "switch_type": "daily_task",
            "interval_hours": 1,
            "grace_period_hours": 0,
            "penalty_xp": 75,
            "is_enabled": True,
        },
    )
    assert cfg_resp.status_code == 200

    # 3. Status endpoint
    status_resp = await auth_client.get("/api/v2/dms/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["count"] >= 2

    # 4. Evaluate overdue rule
    stmt = select(DeadMansSwitchRule).where(
        DeadMansSwitchRule.user_id == user.id,
        DeadMansSwitchRule.switch_type == "daily_task",
    )
    rule = (await db_session.execute(stmt)).scalar_one()
    # Artificially age the deadline into the past
    rule.next_deadline_at = datetime.now(UTC) - timedelta(hours=3)
    await db_session.flush()

    eval_res = await evaluate_all_dead_mans_switches(db_session)
    assert eval_res["violations_count"] >= 1

    await db_session.refresh(rule)
    assert rule.status == "triggered_penalty"
    assert rule.miss_count >= 1
