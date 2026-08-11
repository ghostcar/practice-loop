"""Tests for universal media assets + verification challenges."""

from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import MediaAsset, VerificationChallenge
from app.models.user import User
from app.services.media import (
    compute_code_hmac,
    generate_verification_code,
    verify_code_constant_time,
)

pytestmark = pytest.mark.anyio


# ── Verification code generation ──


class TestCodeGeneration:
    def test_default_length(self):
        code = generate_verification_code()
        assert len(code) == 7
        # No ambiguous chars
        assert all(c in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" for c in code)

    def test_custom_length(self):
        for length in (4, 8, 12, 16):
            code = generate_verification_code(length)
            assert len(code) == length

    def test_uniqueness(self):
        codes = {generate_verification_code() for _ in range(50)}
        assert len(codes) == 50  # all unique

    def test_hmac_verification(self):
        code = generate_verification_code()
        hmac_val = compute_code_hmac(code)
        assert len(hmac_val) == 64  # SHA-256

        assert verify_code_constant_time(code, hmac_val) is True
        assert verify_code_constant_time("WRONG1", hmac_val) is False
        assert verify_code_constant_time("", hmac_val) is False

    def test_constant_time_rejects_wrong_length(self):
        code = "ABCDEFG"
        hmac_val = compute_code_hmac(code)
        assert verify_code_constant_time("SHORT", hmac_val) is False


# ── MediaAsset model ──


class TestMediaAssetModel:
    async def test_create_staged_asset(self, db_session: AsyncSession, test_user: User) -> None:
        asset = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="staged",
            file_path="/uploads/media/abc.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1024,
            sha256_hex=hashlib.sha256(b"test").hexdigest(),
            width=100,
            height=200,
        )
        db_session.add(asset)
        await db_session.flush()

        result = await db_session.execute(select(MediaAsset).where(MediaAsset.owner_id == test_user.id))
        saved = result.scalar_one()
        assert saved.state == "staged"
        assert saved.mime_type == "image/jpeg"
        assert saved.width == 100

    async def test_cross_user_isolation(self, db_session: AsyncSession, test_user: User) -> None:
        asset = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="staged",
            file_path="/uploads/media/x.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(asset)
        await db_session.flush()

        other_id = uuid.uuid4()
        result = await db_session.execute(select(MediaAsset).where(MediaAsset.owner_id == other_id))
        assert result.scalar_one_or_none() is None


# ── VerificationChallenge model ──


class TestVerificationChallengeModel:
    async def test_create_challenge(self, db_session: AsyncSession, test_user: User) -> None:
        from datetime import UTC, datetime, timedelta

        code = generate_verification_code()
        hmac_val = compute_code_hmac(code)
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=uuid.uuid4(),
            code_hmac=hmac_val,
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        await db_session.flush()

        result = await db_session.execute(
            select(VerificationChallenge).where(VerificationChallenge.owner_id == test_user.id)
        )
        saved = result.scalar_one()
        assert saved.state == "active"
        assert saved.max_attempts == 5

    async def test_challenge_cross_user_isolation(self, db_session: AsyncSession, test_user: User) -> None:
        from datetime import UTC, datetime, timedelta

        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="test",
            owner_ref_id=uuid.uuid4(),
            code_hmac="a" * 64,
            code_length=7,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        await db_session.flush()

        other_id = uuid.uuid4()
        result = await db_session.execute(
            select(VerificationChallenge).where(VerificationChallenge.owner_id == other_id)
        )
        assert result.scalar_one_or_none() is None


# ── Media API integration tests ──


class TestMediaApi:
    async def test_upload_endpoint(self, auth_client, test_user: User) -> None:
        """Upload a small JPEG (1x1 pixel)."""
        # Smallest valid JPEG (1x1 pixel, 119 bytes)
        data = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
            b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a"
            b"\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f"
            b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02"
            b"\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00"
            b'\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1'
            b"\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJS"
            b"TUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95"
            b"\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5"
            b"\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5"
            b"\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3"
            b"\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2"
            b"\xcf \x00\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01"
            b"\xff\xd9"
        )
        files = {"file": ("test.jpg", io.BytesIO(data), "image/jpeg")}
        response = await auth_client.post("/api/v1/media?owner_type=general", files=files)
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "staged"
        assert body["mime_type"] == "image/jpeg"
        assert body["file_size_bytes"] > 0

    async def test_upload_rejects_bad_mime(self, auth_client) -> None:
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        response = await auth_client.post("/api/v1/media?owner_type=general", files=files)
        assert response.status_code == 400

    async def test_list_media(self, auth_client, test_user: User) -> None:
        response = await auth_client.get("/api/v1/media")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_media_requires_auth(self, async_client) -> None:
        response = await async_client.get("/api/v1/media")
        assert response.status_code in (401, 403)

    async def test_delete_staged(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        asset = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="staged",
            file_path="/uploads/media/test.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(asset)

        response = await auth_client.delete(f"/api/v1/media/{asset.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


# ── Verification API integration tests ──


class TestVerificationApi:
    async def test_create_and_verify_challenge(self, auth_client) -> None:
        ref_id = str(uuid.uuid4())
        response = await auth_client.post(
            "/api/v1/verification/challenges",
            json={"owner_type": "lock_session", "owner_ref_id": ref_id},
        )
        assert response.status_code == 200
        body = response.json()
        assert "code" in body
        assert len(body["code"]) == 7
        challenge_id = body["id"]

        # Verify with correct code
        verify_resp = await auth_client.post(
            f"/api/v1/verification/challenges/{challenge_id}/verify",
            json={"code": body["code"]},
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["verified"] is True

        # Re-verify should fail (already consumed)
        verify_resp2 = await auth_client.post(
            f"/api/v1/verification/challenges/{challenge_id}/verify",
            json={"code": body["code"]},
        )
        assert verify_resp2.status_code == 409

    async def test_verify_wrong_code(self, auth_client) -> None:
        ref_id = str(uuid.uuid4())
        response = await auth_client.post(
            "/api/v1/verification/challenges",
            json={"owner_type": "lock_session", "owner_ref_id": ref_id},
        )
        challenge_id = response.json()["id"]

        # Wrong code — different char set, should fail
        verify_resp = await auth_client.post(
            f"/api/v1/verification/challenges/{challenge_id}/verify",
            json={"code": "0000000"},
        )
        assert verify_resp.status_code == 403

    async def test_status_endpoint_never_returns_code(self, auth_client) -> None:
        ref_id = str(uuid.uuid4())
        create_resp = await auth_client.post(
            "/api/v1/verification/challenges",
            json={"owner_type": "lock_session", "owner_ref_id": ref_id},
        )
        challenge_id = create_resp.json()["id"]

        status_resp = await auth_client.get(f"/api/v1/verification/challenges/{challenge_id}")
        assert status_resp.status_code == 200
        assert "code" not in status_resp.json()
        assert status_resp.json()["state"] == "active"

    async def test_cross_user_challenge_not_found(self, auth_client) -> None:
        random_id = str(uuid.uuid4())
        response = await auth_client.get(f"/api/v1/verification/challenges/{random_id}")
        assert response.status_code == 404

    async def test_new_challenge_invalidates_previous(self, auth_client) -> None:
        ref_id = str(uuid.uuid4())
        c1 = await auth_client.post(
            "/api/v1/verification/challenges",
            json={"owner_type": "lock_session", "owner_ref_id": ref_id},
        )
        c1_id = c1.json()["id"]

        c2 = await auth_client.post(
            "/api/v1/verification/challenges",
            json={"owner_type": "lock_session", "owner_ref_id": ref_id},
        )
        c2_id = c2.json()["id"]

        # First challenge should be expired
        status = await auth_client.get(f"/api/v1/verification/challenges/{c1_id}")
        assert status.json()["state"] == "expired"

        # Second should be active
        status2 = await auth_client.get(f"/api/v1/verification/challenges/{c2_id}")
        assert status2.json()["state"] == "active"
