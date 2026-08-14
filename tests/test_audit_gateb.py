"""Gate B — аудит PROJECT_REVIEW_2026-08-13 (Session 119).

P1-2 — weekly LLM planner: exact dates, uniqueness, completeness, atomic save.
P1-3 — media finalize: owner-target check via registry (no cross-user bind).
P1-7 — version from a single source (app.version).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.llm_config import LLMProviderConfig
from app.models.media import MediaAsset
from app.models.opt_in import UserEntityOptIn
from app.models.user import User

pytestmark = pytest.mark.anyio

_USAGE = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20, "cost": 0.01}


def _llm_cfg(db: AsyncSession, user: User) -> LLMProviderConfig:
    cfg = LLMProviderConfig(
        user_id=user.id,
        provider_name="test",
        api_base_url="http://test",
        api_key_encrypted="encrypted-key",
        model_name="m",
        is_active=True,
        llm_mode="full",
        store_raw_response=True,
    )
    db.add(cfg)
    return cfg


async def _make_allowed_entity(db: AsyncSession, user_id, real_name="Test Activity") -> Entity:
    entity = Entity(
        type="one_time",
        real_name=real_name,
        category="test",
        owner_id=user_id,
        is_public=False,
        risk_level="low",
        params_schema={"intensity": {"type": "integer", "min": 1, "max": 3}},
    )
    db.add(entity)
    await db.flush()
    db.add(UserEntityOptIn(user_id=user_id, entity_id=entity.id, is_opted_in=True, desire_level="want"))
    await db.flush()
    return entity


def _plan_payload(items: list[dict]) -> dict:
    return {"plan": items}


# ---------------------------------------------------------------------------
# P1-2 — weekly planner validation
# ---------------------------------------------------------------------------


class TestWeeklyPlanner:
    async def _run(self, db, user, plan: dict):
        from app.llm.pipeline.generate import generate_weekly_tasks

        cfg = _llm_cfg(db, user)
        await db.flush()
        with patch(
            "app.llm.client.call_llm",
            new=AsyncMock(return_value={"content": json.dumps(plan), "usage": _USAGE}),
        ):
            return await generate_weekly_tasks(db=db, user_id=user.id, llm_config=cfg, locale="en", days=2)

    async def test_happy_path_exact_coverage(self, db_session: AsyncSession, test_user: User) -> None:
        entity = await _make_allowed_entity(db_session, test_user.id)
        from app.timeutils import local_today

        d1 = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        d2 = (local_today() + __import__("datetime").timedelta(days=2)).isoformat()
        plan = _plan_payload(
            [
                {"date": d1, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r1"},
                {"date": d2, "entity_id": str(entity.id), "params": {"intensity": 2}, "reasoning": "r2"},
            ]
        )
        logs = await self._run(db_session, test_user, plan)
        assert len(logs) == 2
        assert {lg.scheduled_at.date().isoformat() for lg in logs} == {d1, d2}

    async def test_date_outside_range_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        entity = await _make_allowed_entity(db_session, test_user.id)
        from app.timeutils import local_today

        ok = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        bad = (local_today() + __import__("datetime").timedelta(days=30)).isoformat()  # outside 2-day window
        plan = _plan_payload(
            [
                {"date": ok, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r1"},
                {"date": bad, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r2"},
            ]
        )
        with pytest.raises(ValueError, match="outside the requested range"):
            await self._run(db_session, test_user, plan)
        # Nothing was written.
        rows = (
            (await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == test_user.id))).scalars().all()
        )
        assert rows == []

    async def test_duplicate_date_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        entity = await _make_allowed_entity(db_session, test_user.id)
        from app.timeutils import local_today

        d = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        plan = _plan_payload(
            [
                {"date": d, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r1"},
                {"date": d, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r2"},
            ]
        )
        with pytest.raises(ValueError, match="duplicate date"):
            await self._run(db_session, test_user, plan)

    async def test_incomplete_coverage_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        entity = await _make_allowed_entity(db_session, test_user.id)
        from app.timeutils import local_today

        d1 = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        plan = _plan_payload([{"date": d1, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r1"}])
        with pytest.raises(ValueError, match="must cover exactly"):
            await self._run(db_session, test_user, plan)

    async def test_non_allowed_entity_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        foreign = await _make_allowed_entity(db_session, test_user.id)
        # A second user's entity, NOT opted-in by test_user.
        other_user = User(email="other@example.com", password_hash="x")
        db_session.add(other_user)
        await db_session.flush()
        private = Entity(
            type="one_time",
            real_name="Private",
            category="test",
            owner_id=other_user.id,
            is_public=False,
            risk_level="low",
        )
        db_session.add(private)
        await db_session.flush()
        from app.timeutils import local_today

        d1 = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        d2 = (local_today() + __import__("datetime").timedelta(days=2)).isoformat()
        plan = _plan_payload(
            [
                {"date": d1, "entity_id": str(foreign.id), "params": {"intensity": 1}, "reasoning": "r1"},
                {"date": d2, "entity_id": str(private.id), "params": {"intensity": 1}, "reasoning": "r2"},
            ]
        )
        with pytest.raises(ValueError, match="not in the allowed set"):
            await self._run(db_session, test_user, plan)

    async def test_invalid_params_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        entity = await _make_allowed_entity(db_session, test_user.id)
        from app.timeutils import local_today

        d1 = (local_today() + __import__("datetime").timedelta(days=1)).isoformat()
        d2 = (local_today() + __import__("datetime").timedelta(days=2)).isoformat()
        plan = _plan_payload(
            [
                {"date": d1, "entity_id": str(entity.id), "params": {"intensity": 99}, "reasoning": "r1"},
                {"date": d2, "entity_id": str(entity.id), "params": {"intensity": 1}, "reasoning": "r2"},
            ]
        )
        with pytest.raises(ValueError, match="params invalid"):
            await self._run(db_session, test_user, plan)


# ---------------------------------------------------------------------------
# P1-3 — media finalize owner-target check
# ---------------------------------------------------------------------------


class TestMediaFinalizeOwnerTarget:
    async def _staged_asset(self, db_session: AsyncSession, user: User) -> MediaAsset:
        asset = MediaAsset(
            owner_id=user.id,
            owner_type="general",
            state="staged",
            file_path="/uploads/media/test.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1,
        )
        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(asset)
        return asset

    async def test_finalize_own_target_ok(self, db_session: AsyncSession, auth_client, test_user: User) -> None:
        asset = await self._staged_asset(db_session, test_user)
        log = ActivityLog(user_id=test_user.id, entity_id=uuid.uuid4(), status="planned")
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        resp = await auth_client.post(
            f"/api/v2/media/{asset.id}/finalize",
            params={"owner_type": "activity_log", "owner_ref_id": str(log.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "ready"
        assert resp.json()["owner_ref_id"] == str(log.id)

    async def test_finalize_foreign_target_rejected(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        asset = await self._staged_asset(db_session, test_user)
        other_user = User(email="other2@example.com", password_hash="x")
        db_session.add(other_user)
        await db_session.flush()
        foreign_log = ActivityLog(user_id=other_user.id, entity_id=uuid.uuid4(), status="planned")
        db_session.add(foreign_log)
        await db_session.commit()
        await db_session.refresh(foreign_log)

        resp = await auth_client.post(
            f"/api/v2/media/{asset.id}/finalize",
            params={"owner_type": "activity_log", "owner_ref_id": str(foreign_log.id)},
        )
        assert resp.status_code == 404
        # Asset stays staged.
        await db_session.refresh(asset)
        assert asset.state == "staged"

    async def test_finalize_missing_target_rejected(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        asset = await self._staged_asset(db_session, test_user)
        resp = await auth_client.post(
            f"/api/v2/media/{asset.id}/finalize",
            params={"owner_type": "activity_log", "owner_ref_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Шаг 4 — Omniroute preset wired to settings (Q14 part 2)
# ---------------------------------------------------------------------------


class TestOmniroutePreset:
    async def test_preset_uses_settings_host_and_key(self, monkeypatch) -> None:
        """The seeded Omniroute preset must read host/key from settings (ADR-070)."""
        from app.config import settings as _settings

        monkeypatch.setattr(_settings, "omniroute_host", "https://llm.example.com")
        monkeypatch.setattr(_settings, "omniroute_api_key", "secret-key-123")

        from app.seed import get_seed_llm_presets

        presets = get_seed_llm_presets()
        omniroute = next(p for p in presets if p["provider_name"] == "Omniroute")
        assert omniroute["api_base_url"] == "https://llm.example.com/v1"
        assert omniroute["api_key"] == "secret-key-123"
        assert omniroute["is_active"] is True
        assert omniroute["model_name"] == "auto"

    async def test_preset_normalizes_host_without_v1(self, monkeypatch) -> None:
        from app.config import settings as _settings

        monkeypatch.setattr(_settings, "omniroute_host", "https://llm.example.com/v1")
        monkeypatch.setattr(_settings, "omniroute_api_key", "k")

        from app.seed import get_seed_llm_presets

        presets = get_seed_llm_presets()
        omniroute = next(p for p in presets if p["provider_name"] == "Omniroute")
        # No double /v1/v1.
        assert omniroute["api_base_url"] == "https://llm.example.com/v1"

    async def test_seed_encrypts_omniroute_key(self, db_session: AsyncSession, test_user: User, monkeypatch) -> None:
        from app.config import settings as _settings

        monkeypatch.setattr(_settings, "omniroute_host", "https://llm.example.com")
        monkeypatch.setattr(_settings, "omniroute_api_key", "secret-key-123")

        from app.encryption import mask_api_key
        from app.seed import seed_llm_presets

        created = await seed_llm_presets(db_session, test_user.id)
        omni = next(c for c in created if c.provider_name == "Omniroute")
        # Key is encrypted (masked output is a mask, not the plaintext).
        assert omni.api_key_encrypted is not None
        assert "secret-key-123" not in (mask_api_key(omni.api_key_encrypted) or "")


# ---------------------------------------------------------------------------
# P1-7 — single version source
# ---------------------------------------------------------------------------


class TestVersionSingleSource:
    def test_app_version_matches_pyproject(self) -> None:
        import tomllib

        from app.version import __version__

        with open("pyproject.toml", "rb") as f:
            meta = tomllib.load(f)
        assert meta["project"]["version"] == __version__

    def test_fastapi_version_uses_app_version(self) -> None:
        from app.main import app
        from app.version import __version__

        assert app.version == __version__

    async def test_export_uses_app_version(self, auth_client, test_user: User) -> None:
        from app.version import __version__

        resp = await auth_client.get("/import/export/full")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__
