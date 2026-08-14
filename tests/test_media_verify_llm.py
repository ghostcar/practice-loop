"""Tests for Step 7 — LLM media verification (ADR-075).

Covers:
1. Engine — verdict parsing, code_match (LLM compare), chastity_closed,
   challenge read-mode (server HMAC is the authority), file-not-found.
2. API — POST verify (expected_code path, challenge auto-consume path),
   no-config 409, missing code/challenge 400, cross-user 404,
   results list, page GET/POST rendering.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.pipeline.media_verify import (
    _parse_verdict,
    find_active_challenge,
    verify_media_with_llm,
)
from app.models.llm_config import LLMProviderConfig
from app.models.media import MediaAsset, MediaVerificationResult, VerificationChallenge
from app.models.user import User
from app.services.media import compute_code_hmac, generate_verification_code

pytestmark = pytest.mark.anyio

JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _write_media_file(file_path: str) -> Path:
    """Write a fake image to the upload store; return its absolute path."""
    rel = file_path[len("/uploads/") :]
    full = (Path(settings.upload_dir).resolve() / rel).resolve()
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(JPEG_BYTES)
    return full


def _make_ready_media(db: AsyncSession, user: User, owner_ref_id: uuid.UUID | None = None) -> MediaAsset:
    asset = MediaAsset(
        owner_id=user.id,
        owner_type="lock_session",
        owner_ref_id=owner_ref_id,
        state="ready",
        file_path=f"/uploads/media/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        file_size_bytes=len(JPEG_BYTES),
        sha256_hex=hashlib.sha256(JPEG_BYTES).hexdigest(),
        width=8,
        height=8,
    )
    _write_media_file(asset.file_path)
    db.add(asset)
    return asset


def _make_llm_config(db: AsyncSession, user: User) -> LLMProviderConfig:
    cfg = LLMProviderConfig(
        user_id=user.id,
        provider_name="test",
        api_base_url="http://omniroute.test/v1",
        model_name="openrouter/openai/gpt-4o-mini",
        is_active=True,
    )
    db.add(cfg)
    return cfg


def _fake_call_llm(content: str, usage_tokens: int = 15) -> object:
    async def fake_call_llm(config, system_prompt, user_message, tools=None, json_mode=True, images=None):
        assert images, "vision path must pass image parts"
        return {
            "content": content,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": usage_tokens, "cost": 0.001},
            "tool_calls": [],
        }

    return fake_call_llm


# ── Engine: verdict parsing ──────────────────────────────────────────────────


class TestVerdictParsing:
    def test_valid_verdict(self):
        verdict, conf, reasoning = _parse_verdict('{"verdict": "match", "confidence": 92, "reasoning": "code visible"}')
        assert verdict == "match"
        assert conf == 92
        assert reasoning == "code visible"

    def test_defaults_to_unclear_on_bad_json(self):
        verdict, conf, reasoning = _parse_verdict("not json at all {{{")
        assert verdict == "unclear"
        assert conf == 0

    def test_clamps_confidence(self):
        verdict, conf, _ = _parse_verdict('{"verdict": "match", "confidence": 500}')
        assert conf == 100
        verdict2, conf2, _ = _parse_verdict('{"verdict": "match", "confidence": -5}')
        assert conf2 == 0

    def test_unknown_verdict_becomes_unclear(self):
        verdict, _, _ = _parse_verdict('{"verdict": "maybe", "confidence": 50}')
        assert verdict == "unclear"


# ── Engine: LLM photo evaluation ────────────────────────────────────────────


class TestVerifyEngine:
    async def test_code_match_llm_verdict(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"verdict": "match", "confidence": 88, "reasoning": "code matches"}'),
        )
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        row = await verify_media_with_llm(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            media=media,
            verification_type="code_match",
            expected_code="ABC1234",
            locale="en",
        )
        assert row.verdict == "match"
        assert row.confidence == 88
        assert row.expected_code_hmac == compute_code_hmac("ABC1234")
        assert row.verification_type == "code_match"
        assert row.llm_model == "openrouter/openai/gpt-4o-mini"
        assert row.owner_id == test_user.id
        # usage tracked on config
        assert cfg.total_tokens >= 15

    async def test_chastity_closed_path(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"verdict": "unclear", "confidence": 40, "reasoning": "device not visible"}'),
        )
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        row = await verify_media_with_llm(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            media=media,
            verification_type="chastity_closed",
            locale="en",
        )
        assert row.verdict == "unclear"
        assert row.expected_code_hmac is None

    async def test_challenge_read_mode_match(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        """LLM reads the code; server HMAC is the authority → match."""
        from app.llm import client

        code = generate_verification_code()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=uuid.uuid4(),
            code_hmac=compute_code_hmac(code),
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        await db_session.flush()

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm(f'{{"read_code": "{code}", "confidence": 95, "reasoning": "read from photo"}}'),
        )
        media = _make_ready_media(db_session, test_user, challenge.owner_ref_id)
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        row = await verify_media_with_llm(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            media=media,
            verification_type="code_match",
            expected_code=None,
            locale="en",
            challenge=challenge,
        )
        assert row.verdict == "match"
        assert row.confidence == 95
        assert row.expected_code_hmac == challenge.code_hmac
        # Challenge NOT consumed by the engine — explicit API call only.
        assert challenge.state == "active"

    async def test_challenge_read_mode_mismatch(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        code = generate_verification_code()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=uuid.uuid4(),
            code_hmac=compute_code_hmac(code),
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        await db_session.flush()

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"read_code": "WRONG99", "confidence": 90, "reasoning": "different code"}'),
        )
        media = _make_ready_media(db_session, test_user, challenge.owner_ref_id)
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        row = await verify_media_with_llm(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            media=media,
            verification_type="code_match",
            expected_code=None,
            locale="en",
            challenge=challenge,
        )
        assert row.verdict == "mismatch"

    async def test_challenge_unreadable_code(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        code = generate_verification_code()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=uuid.uuid4(),
            code_hmac=compute_code_hmac(code),
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        await db_session.flush()

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"read_code": null, "confidence": 30, "reasoning": "blurry"}'),
        )
        media = _make_ready_media(db_session, test_user, challenge.owner_ref_id)
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        row = await verify_media_with_llm(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            media=media,
            verification_type="code_match",
            expected_code=None,
            locale="en",
            challenge=challenge,
        )
        assert row.verdict == "unclear"

    async def test_file_not_found(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(client, "call_llm", _fake_call_llm('{"verdict": "match"}'))
        media = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="ready",
            file_path="/uploads/media/missing.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(media)
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        with pytest.raises(FileNotFoundError):
            await verify_media_with_llm(
                db=db_session,
                user_id=test_user.id,
                llm_config=cfg,
                media=media,
                verification_type="chastity_closed",
                locale="en",
            )

    async def test_path_traversal_rejected(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(client, "call_llm", _fake_call_llm('{"verdict": "match"}'))
        media = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="ready",
            file_path="/uploads/../../etc/passwd",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(media)
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()

        with pytest.raises(FileNotFoundError):
            await verify_media_with_llm(
                db=db_session,
                user_id=test_user.id,
                llm_config=cfg,
                media=media,
                verification_type="chastity_closed",
                locale="en",
            )

    async def test_unsupported_type_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        cfg = _make_llm_config(db_session, test_user)
        await db_session.flush()
        with pytest.raises(ValueError):
            await verify_media_with_llm(
                db=db_session,
                user_id=test_user.id,
                llm_config=cfg,
                media=media,
                verification_type="bogus",
                locale="en",
            )


# ── Engine: find_active_challenge ───────────────────────────────────────────


class TestFindActiveChallenge:
    async def test_finds_active(self, db_session: AsyncSession, test_user: User) -> None:
        ref = uuid.uuid4()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=ref,
            code_hmac=compute_code_hmac("ABC1234"),
            code_length=7,
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db_session.add(challenge)
        await db_session.flush()

        found = await find_active_challenge(db_session, test_user.id, "lock_session", ref)
        assert found is not None
        assert found.id == challenge.id

    async def test_ignores_expired(self, db_session: AsyncSession, test_user: User) -> None:
        ref = uuid.uuid4()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=ref,
            code_hmac=compute_code_hmac("ABC1234"),
            code_length=7,
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        db_session.add(challenge)
        await db_session.flush()

        found = await find_active_challenge(db_session, test_user.id, "lock_session", ref)
        assert found is None
        assert challenge.state == "expired"  # lazily marked

    async def test_wrong_owner_type(self, db_session: AsyncSession, test_user: User) -> None:
        ref = uuid.uuid4()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=ref,
            code_hmac=compute_code_hmac("ABC1234"),
            code_length=7,
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db_session.add(challenge)
        await db_session.flush()

        found = await find_active_challenge(db_session, test_user.id, "inventory_item", ref)
        assert found is None


# ── API: POST /api/v2/media/{id}/verify ─────────────────────────────────────


class TestVerifyApi:
    async def test_requires_active_llm_config(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "chastity_closed"},
        )
        assert response.status_code == 409

    async def test_verify_expected_code_path(
        self, auth_client, db_session: AsyncSession, test_user: User, monkeypatch
    ) -> None:
        from app.llm import client

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"verdict": "match", "confidence": 90, "reasoning": "codes equal"}'),
        )
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "code_match", "expected_code": "ABC1234"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "match"
        assert body["confidence"] == 90
        assert body["verification_type"] == "code_match"
        assert body["consumed_challenge"] is None

        # Result persisted
        saved = await db_session.execute(
            select(MediaVerificationResult).where(MediaVerificationResult.media_id == media.id)
        )
        assert saved.scalar_one().verdict == "match"

    async def test_auto_consume_challenge_on_match(
        self, auth_client, db_session: AsyncSession, test_user: User, monkeypatch
    ) -> None:
        from app.llm import client

        code = generate_verification_code()
        ref = uuid.uuid4()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=ref,
            code_hmac=compute_code_hmac(code),
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        media = _make_ready_media(db_session, test_user, ref)
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm(f'{{"read_code": "{code}", "confidence": 95, "reasoning": "visible"}}'),
        )

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "code_match", "auto_consume_challenge": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "match"
        assert body["consumed_challenge"] is not None
        assert body["consumed_challenge"]["id"] == str(challenge.id)

        # Challenge consumed + result references it
        await db_session.refresh(challenge)
        assert challenge.state == "consumed"
        saved = await db_session.execute(
            select(MediaVerificationResult).where(MediaVerificationResult.media_id == media.id)
        )
        assert saved.scalar_one().consumed_challenge_id == challenge.id

    async def test_no_auto_consume_keeps_challenge(
        self, auth_client, db_session: AsyncSession, test_user: User, monkeypatch
    ) -> None:
        from app.llm import client

        code = generate_verification_code()
        ref = uuid.uuid4()
        challenge = VerificationChallenge(
            owner_id=test_user.id,
            owner_type="lock_session",
            owner_ref_id=ref,
            code_hmac=compute_code_hmac(code),
            code_length=len(code),
            state="active",
            max_attempts=5,
            attempt_count=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db_session.add(challenge)
        media = _make_ready_media(db_session, test_user, ref)
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm(f'{{"read_code": "{code}", "confidence": 95, "reasoning": "visible"}}'),
        )

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "code_match", "auto_consume_challenge": False},
        )
        assert response.status_code == 200
        assert response.json()["consumed_challenge"] is None
        await db_session.refresh(challenge)
        assert challenge.state == "active"

    async def test_missing_code_and_challenge_is_400(
        self, auth_client, db_session: AsyncSession, test_user: User
    ) -> None:
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "code_match"},
        )
        assert response.status_code == 400

    async def test_cross_user_404(self, auth_client, db_session: AsyncSession) -> None:
        other = User(email="other@example.com", password_hash="x", locale="en", theme="light")
        db_session.add(other)
        await db_session.flush()
        media = _make_ready_media(db_session, other, uuid.uuid4())
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "chastity_closed"},
        )
        assert response.status_code == 404

    async def test_staged_media_rejected(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        media = MediaAsset(
            owner_id=test_user.id,
            owner_type="general",
            state="staged",
            file_path="/uploads/media/x.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(media)
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "chastity_closed"},
        )
        assert response.status_code == 409

    async def test_results_listing(self, auth_client, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"verdict": "match", "confidence": 80, "reasoning": "ok"}'),
        )
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        await auth_client.post(
            f"/api/v2/media/{media.id}/verify",
            json={"verification_type": "chastity_closed"},
        )

        response = await auth_client.get(f"/api/v2/media/{media.id}/verification-results")
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["verdict"] == "match"


# ── Page ────────────────────────────────────────────────────────────────────


class TestVerifyPage:
    async def test_page_renders(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        _make_ready_media(db_session, test_user, uuid.uuid4())
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        response = await auth_client.get("/llm/verify")
        assert response.status_code == 200
        assert "Media Verification" in response.text or "Верификация" in response.text

    async def test_page_post_flow(self, auth_client, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.llm import client

        monkeypatch.setattr(
            client,
            "call_llm",
            _fake_call_llm('{"verdict": "unclear", "confidence": 20, "reasoning": "too dark"}'),
        )
        media = _make_ready_media(db_session, test_user, uuid.uuid4())
        _make_llm_config(db_session, test_user)
        await db_session.flush()

        response = await auth_client.post(
            "/llm/verify",
            data={
                "media_id": str(media.id),
                "verification_type": "chastity_closed",
            },
        )
        assert response.status_code == 200
        assert "Unclear" in response.text or "Неясно" in response.text
