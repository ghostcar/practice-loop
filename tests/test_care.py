"""Personal Care tests (M3 Personal Suite, Шаг 15, ROADMAP §7 4B).

Relief-only: уход без игровой интеграции (PD-013). Приватные записи,
связь с Cycle — снимок расчётной фазы (не факт), медиа — через
owner_type=care_entry (owner-scoped).
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.care import CareEntry, CareRoutine
from app.models.media import MediaAsset
from app.models.user import User

TODAY = date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Page + routines
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_care_page_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "care_no_routines" in resp.text or "No procedures yet" in resp.text


@pytest.mark.asyncio
async def test_add_routine_and_list(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/care/routines",
        data={
            "name": "Night skincare",
            "area": "face",
            "kind": "home",
            "frequency_days": "7",
            "notes": "serum + cream",
        },
    )
    assert resp.status_code == 303, resp.text
    routines = (
        (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalars().all()
    )
    assert len(routines) == 1
    r = routines[0]
    assert r.name == "Night skincare"
    assert r.area == "face"
    assert r.kind == "home"
    assert r.frequency_days == 7
    assert r.notes == "serum + cream"

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Night skincare" in resp.text


@pytest.mark.asyncio
async def test_add_routine_invalid_area_defaults(auth_client, test_user, db_session):
    resp = await auth_client.post("/care/routines", data={"name": "Laser", "area": "bogus", "kind": "weird"})
    assert resp.status_code == 303, resp.text
    r = (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalar_one()
    assert r.area == "other"
    assert r.kind == "home"


@pytest.mark.asyncio
async def test_delete_routine_sets_null(auth_client, test_user, db_session):
    await auth_client.post("/care/routines", data={"name": "Mask"})
    routine = (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalar_one()
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat(), "routine_id": str(routine.id)})
    resp = await auth_client.post(f"/care/routines/{routine.id}/delete")
    assert resp.status_code == 303
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    assert entry.routine_id is None  # SET NULL — связь по ID без раскрытия


# ─────────────────────────────────────────────────────────────────────────────
# Entries
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_entry_and_list(auth_client, test_user, db_session):
    await auth_client.post("/care/routines", data={"name": "Depilation"})
    routine = (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalar_one()
    resp = await auth_client.post(
        "/care/entries",
        data={
            "entry_date": TODAY.isoformat(),
            "routine_id": str(routine.id),
            "duration_minutes": "30",
            "skin_reaction": "4",
            "notes": "smooth",
        },
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    assert entry.routine_id == routine.id
    assert entry.duration_minutes == 30
    assert entry.skin_reaction == 4
    assert entry.notes == "smooth"

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Depilation" in resp.text
    assert "smooth" in resp.text


@pytest.mark.asyncio
async def test_place_fields_form_and_display(auth_client, test_user, db_session):
    """Место проведения (салон, адрес) сохраняется и показывается на /care (2026-08-19)."""
    resp = await auth_client.post(
        "/care/routines",
        data={
            "name": "Laser hair removal",
            "area": "body",
            "kind": "salon",
            "place_name": "Lotus salon",
            "place_address": "12 Tverskaya St",
        },
    )
    assert resp.status_code == 303, resp.text
    routine = (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalar_one()
    assert routine.place_name == "Lotus salon"
    assert routine.place_address == "12 Tverskaya St"

    resp = await auth_client.post(
        "/care/entries",
        data={
            "entry_date": TODAY.isoformat(),
            "routine_id": str(routine.id),
            "place_name": "Lotus salon",
            "place_address": "12 Tverskaya St",
        },
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    assert entry.place_name == "Lotus salon"
    assert entry.place_address == "12 Tverskaya St"

    resp = await auth_client.post(
        "/care/courses",
        data={
            "name": "Laser course",
            "place_name": "Lotus salon",
            "place_address": "12 Tverskaya St",
            "total_sessions": "3",
        },
    )
    assert resp.status_code == 303, resp.text

    page = await auth_client.get("/care")
    assert page.status_code == 200
    assert "Lotus salon" in page.text
    assert "12 Tverskaya St" in page.text


@pytest.mark.asyncio
async def test_json_place_fields(auth_client, test_user, db_session):
    """Место проведения доступно в JSON API (routine/entry/course)."""
    resp = await auth_client.post(
        "/api/v2/care/routines",
        json={
            "name": "Manicure",
            "area": "hands",
            "kind": "salon",
            "place_name": "Nail bar",
            "place_address": "5 Arbat St",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["place_name"] == "Nail bar"
    assert resp.json()["place_address"] == "5 Arbat St"

    resp = await auth_client.post(
        "/api/v2/care/entries",
        json={"entry_date": TODAY.isoformat(), "place_name": "Nail bar", "place_address": "5 Arbat St"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["place_name"] == "Nail bar"
    assert resp.json()["place_address"] == "5 Arbat St"

    resp = await auth_client.post(
        "/api/v2/care/courses",
        json={"name": "Pedicure course", "place_name": "Nail bar", "place_address": "5 Arbat St", "total_sessions": 4},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["place_name"] == "Nail bar"
    assert resp.json()["place_address"] == "5 Arbat St"


@pytest.mark.asyncio
async def test_invalid_reaction_rejected(auth_client, test_user, db_session):
    resp = await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat(), "skin_reaction": "9"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_foreign_routine_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_routine = CareRoutine(user_id=other.id, name="X")
    db_session.add(other_routine)
    await db_session.flush()

    resp = await auth_client.post(
        "/care/entries", data={"entry_date": TODAY.isoformat(), "routine_id": str(other_routine.id)}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_entry(auth_client, test_user, db_session):
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat()})
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    resp = await auth_client.post(f"/care/entries/{entry.id}/delete")
    assert resp.status_code == 303
    remaining = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalars().all()
    assert len(remaining) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot (связь Personal Care ↔ Cycle, §9.4)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_snapshots_cycle_phase(auth_client, test_user, db_session):
    start = TODAY - timedelta(days=5)
    await auth_client.post("/health/cycle/events", data={"event_date": start.isoformat(), "event_type": "bleeding"})
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat(), "notes": "x"})
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    assert entry.cycle_phase == "follicular"
    assert entry.cycle_day == 6


# ─────────────────────────────────────────────────────────────────────────────
# Media binding
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_media_upload_binds_asset(auth_client, test_user, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat()})
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    resp = await auth_client.post(
        f"/care/entries/{entry.id}/media",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
        data={"caption": "progress"},
    )
    assert resp.status_code == 303, resp.text

    asset = (await db_session.execute(select(MediaAsset).where(MediaAsset.owner_id == test_user.id))).scalar_one()
    assert asset.owner_type == "care_entry"
    assert asset.owner_ref_id == entry.id
    assert asset.caption == "progress"
    assert asset.state == "ready"


@pytest.mark.asyncio
async def test_entry_media_rejects_foreign_entry(auth_client, test_user, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_entry = CareEntry(user_id=other.id, entry_date=TODAY)
    db_session.add(other_entry)
    await db_session.flush()

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    resp = await auth_client.post(
        f"/care/entries/{other_entry.id}/media",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_summary_and_add(auth_client, test_user, db_session):
    resp = await auth_client.post("/api/v2/care/routines", json={"name": "Manicure", "area": "hands", "kind": "salon"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["area"] == "hands"

    routine_id = resp.json()["id"]
    resp = await auth_client.post(
        "/api/v2/care/entries",
        json={"entry_date": TODAY.isoformat(), "routine_id": routine_id, "skin_reaction": 5},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["skin_reaction"] == 5

    resp = await auth_client.get("/api/v2/care")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 1
    assert len(data["routines"]) == 1


@pytest.mark.asyncio
async def test_json_foreign_routine_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_routine = CareRoutine(user_id=other.id, name="X")
    db_session.add(other_routine)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/care/entries",
        json={"entry_date": TODAY.isoformat(), "routine_id": str(other_routine.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_json_delete_entry_and_routine(auth_client, test_user, db_session):
    """DELETE /api/v2/care/{entries,routines}/{id} — 204 and removed from summary."""
    routine = (await auth_client.post("/api/v2/care/routines", json={"name": "Manicure", "area": "hands"})).json()
    entry = (
        await auth_client.post(
            "/api/v2/care/entries",
            json={"entry_date": TODAY.isoformat(), "routine_id": routine["id"]},
        )
    ).json()

    resp = await auth_client.delete(f"/api/v2/care/entries/{entry['id']}")
    assert resp.status_code == 204, resp.text
    summary = (await auth_client.get("/api/v2/care")).json()
    assert summary["total_entries"] == 0

    resp = await auth_client.delete(f"/api/v2/care/routines/{routine['id']}")
    assert resp.status_code == 204, resp.text
    summary = (await auth_client.get("/api/v2/care")).json()
    assert len(summary["routines"]) == 0


@pytest.mark.asyncio
async def test_json_delete_routine_preserves_entries(auth_client, test_user, db_session):
    """Deleting a routine keeps its entries (routine_id → None)."""
    routine = (await auth_client.post("/api/v2/care/routines", json={"name": "Mask", "area": "face"})).json()
    await auth_client.post(
        "/api/v2/care/entries",
        json={"entry_date": TODAY.isoformat(), "routine_id": routine["id"]},
    )

    resp = await auth_client.delete(f"/api/v2/care/routines/{routine['id']}")
    assert resp.status_code == 204

    summary = (await auth_client.get("/api/v2/care")).json()
    assert len(summary["routines"]) == 0
    assert summary["total_entries"] == 1
    entries = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalars().all()
    assert len(entries) == 1
    assert entries[0].routine_id is None


@pytest.mark.asyncio
async def test_json_delete_foreign_rejected(auth_client, test_user, db_session):
    """DELETE of another user's routine → 404 (owner-scoped)."""
    other = User(email="other-del@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_routine = CareRoutine(user_id=other.id, name="X")
    db_session.add(other_routine)
    await db_session.flush()

    resp = await auth_client.delete(f"/api/v2/care/routines/{other_routine.id}")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat(), "notes": "private"})
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    resp = await auth_client.get("/api/v2/care")
    assert resp.status_code == 200
    assert not any("private" in (e.get("notes") or "") for e in resp.json()["entries"])


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard block
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_care_block(auth_client, test_user, db_session):
    await auth_client.post("/care/entries", data={"entry_date": TODAY.isoformat(), "skin_reaction": "5"})
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-care"' in html
    assert "dash_care_entries_30d" in html or "procedures in 30d" in html


@pytest.mark.asyncio
async def test_dashboard_care_block_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    assert 'id="dash-block-care"' in resp.text
    assert "dash_care_empty" in resp.text or "No care entries yet" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_care_module_no_gamification():
    """PD-013: уход не применяет игровую механику (по импортам и вызовам)."""
    import inspect

    import app.api.care as mod
    import app.models.care as models

    for source in (inspect.getsource(mod), inspect.getsource(models)):
        assert "app.gamification" not in source
        assert "app.models.points" not in source
        assert "app.models.progress" not in source
        assert "award_points" not in source
        assert "apply_penalty" not in source
        assert "calculate_entity_penalty" not in source
