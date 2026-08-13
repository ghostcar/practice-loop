"""Authorized upload serving — audit P0-1 regression tests.

The public `/uploads` static mount was removed. Files are now served through
`GET /uploads/{path}` with authentication + owner reverse-lookup. These tests
cover: containment (traversal), owner 200, cross-user 404, anonymous 401,
and missing-file 404.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.uploads import resolve_upload_path
from app.config import settings
from app.models.attachment import Attachment
from app.models.user import User

pytestmark = pytest.mark.anyio


class TestResolveUploadPath:
    def test_valid(self, tmp_path):
        assert resolve_upload_path(Path(tmp_path), "attachments/a.jpg") == (tmp_path / "attachments/a.jpg").resolve()

    def test_traversal_rejected(self, tmp_path):
        assert resolve_upload_path(Path(tmp_path), "../secret.txt") is None
        assert resolve_upload_path(Path(tmp_path), "a/../../secret.txt") is None

    def test_absolute_rejected(self, tmp_path):
        assert resolve_upload_path(Path(tmp_path), "/etc/passwd") is None

    def test_backslash_rejected(self, tmp_path):
        assert resolve_upload_path(Path(tmp_path), "..\\secret.txt") is None

    def test_empty_rejected(self, tmp_path):
        assert resolve_upload_path(Path(tmp_path), "") is None


class TestUploadServing:
    @pytest.fixture
    def _upload_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _make_attachment(self, db_session: AsyncSession, owner: User, name: str) -> Attachment:
        att = Attachment(
            user_id=owner.id,
            owner_type="diet",
            owner_id=uuid.uuid4(),
            file_path=f"/uploads/attachments/{name}",
            caption=None,
            sort_order=0,
        )
        db_session.add(att)
        await db_session.commit()
        await db_session.refresh(att)
        return att

    async def test_owner_can_serve(self, _upload_dir, db_session, auth_client, test_user):
        (_upload_dir / "attachments").mkdir(parents=True)
        (_upload_dir / "attachments" / "photo.jpg").write_bytes(b"\xff\xd8\xff\x00")
        await self._make_attachment(db_session, test_user, "photo.jpg")

        resp = await auth_client.get("/uploads/attachments/photo.jpg")
        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.content == b"\xff\xd8\xff\x00"

    async def test_missing_file_404(self, _upload_dir, db_session, auth_client, test_user):
        await self._make_attachment(db_session, test_user, "gone.jpg")
        resp = await auth_client.get("/uploads/attachments/gone.jpg")
        assert resp.status_code == 404

    async def test_cross_user_404(self, _upload_dir, db_session, auth_client, test_user):
        (_upload_dir / "attachments").mkdir(parents=True)
        (_upload_dir / "attachments" / "photo.jpg").write_bytes(b"x")

        other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
        db_session.add(other)
        await db_session.flush()
        await self._make_attachment(db_session, other, "photo.jpg")

        # auth_client is authenticated as test_user, not `other`.
        resp = await auth_client.get("/uploads/attachments/photo.jpg")
        assert resp.status_code == 404

    async def test_anonymous_401(self, _upload_dir, db_session, async_client, test_user):
        (_upload_dir / "attachments").mkdir(parents=True)
        (_upload_dir / "attachments" / "photo.jpg").write_bytes(b"x")
        await self._make_attachment(db_session, test_user, "photo.jpg")

        resp = await async_client.get("/uploads/attachments/photo.jpg")
        assert resp.status_code in (401, 403)

    async def test_traversal_404(self, _upload_dir, auth_client):
        resp = await auth_client.get("/uploads/../README.md")
        assert resp.status_code in (404, 403)
