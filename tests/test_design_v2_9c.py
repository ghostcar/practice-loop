"""Tests for Step 9c — Inventory / Media patterns (DESIGN_V2 §10/§11).

Covers:
1. /media page renders the gallery shell (title, empty state) for authed user.
2. Upload from the vault stages an asset and it appears in the gallery.
3. Verified state badge appears after a verification result exists.
4. Inventory page renders; nav points Media Vault to /media.
5. New i18n keys exist in both locales.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.en import EN
from app.i18n.ru import RU
from app.models.media import MediaAsset, MediaVerificationResult
from app.models.user import User

pytestmark = pytest.mark.anyio

I18N_KEYS_9C = [
    "mvt_title",
    "mvt_subtitle",
    "mvt_upload",
    "mvt_state_staged",
    "mvt_state_ready",
    "mvt_state_archived",
    "mvt_verdict_match",
    "mvt_verdict_mismatch",
    "mvt_verdict_unclear",
    "mvt_not_verified",
    "mvt_retention_private",
    "mvt_retention_archived",
    "mvt_empty",
    "mvt_empty_hint",
]

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


class TestMediaVaultPage:
    async def test_page_renders_empty_state(self, auth_client):
        resp = await auth_client.get("/media")
        assert resp.status_code == 200
        assert "Media Vault" in resp.text
        assert "mvt_empty" in resp.text or "No media yet" in resp.text

    async def test_upload_stages_asset_and_shows_it(self, auth_client, db_session: AsyncSession, test_user: User):
        files = {"file": ("photo.jpg", io.BytesIO(JPEG), "image/jpeg")}
        resp = await auth_client.post("/media/upload", files=files)
        assert resp.status_code == 303
        assert resp.headers.get("location", "").endswith("/media")

        # Asset staged in DB
        stmt = select(MediaAsset).where(MediaAsset.owner_id == test_user.id)
        assets = (await db_session.execute(stmt)).scalars().all()
        assert len(assets) == 1
        assert assets[0].state == "staged"

        # Gallery shows it now (staged chip + no-verified badge)
        page = await auth_client.get("/media")
        assert page.status_code == 200
        assert assets[0].id.hex[:8] in page.text or "Staged" in page.text

    async def test_verification_badge_rendered(self, auth_client, db_session: AsyncSession, test_user: User):
        files = {"file": ("photo.jpg", io.BytesIO(JPEG), "image/jpeg")}
        await auth_client.post("/media/upload", files=files)
        stmt = select(MediaAsset).where(MediaAsset.owner_id == test_user.id)
        asset = (await db_session.execute(stmt)).scalars().one()

        # Attach an LLM verification result (match)
        result = MediaVerificationResult(
            owner_id=test_user.id,
            media_id=asset.id,
            verification_type="code_match",
            verdict="match",
            confidence=92,
            reasoning="code visible",
        )
        db_session.add(result)
        await db_session.commit()

        page = await auth_client.get("/media")
        assert page.status_code == 200
        assert "Verified" in page.text or "mvt_verdict_match" in page.text
        assert "code match" in page.text or "mv_type_code_match" in page.text

    async def test_media_in_sidebar_points_to_vault(self, auth_client):
        resp = await auth_client.get("/dashboard")
        assert 'href="/media"' in resp.text
        # Old nav target (JSON list endpoint) is gone from the shell
        assert 'href="/api/v2/media"' not in resp.text


class TestInventoryPage:
    async def test_inventory_page_renders(self, auth_client):
        resp = await auth_client.get("/api/v2/inventory/page")
        assert resp.status_code == 200
        assert 'id="inv-list"' in resp.text


class TestI18n9c:
    def test_keys_in_both_locales(self):
        for key in I18N_KEYS_9C:
            assert key in EN, f"missing EN key: {key}"
            assert key in RU, f"missing RU key: {key}"
            assert EN[key].strip(), f"empty EN value: {key}"
            assert RU[key].strip(), f"empty RU value: {key}"
