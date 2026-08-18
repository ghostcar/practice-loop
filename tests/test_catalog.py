"""Universal Activity Catalog tests (ADR-091, Шаг 16).

Сквозной каталог активностей: системные + свои записи, замена свободных полей
на FK-ссылку, интеграция в журнал/уход/таймер/трекер. Каталог нейтрален
(relief-only, PD-013) — без игровой интеграции.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.care import CareRoutine
from app.models.catalog import ActivityCatalogItem
from app.models.journal import JournalEntry
from app.models.locktimer import LockSlotRule
from app.models.user import User

TODAY = date.today()


async def _system_item(db, name: str = "Массаж") -> ActivityCatalogItem:
    """Create a system catalog item (owner_id NULL)."""
    item = ActivityCatalogItem(name=name, domains=["journal", "care", "tracker"], tags=["touch"])
    db.add(item)
    await db.flush()
    return item


async def _own_item(db, user_id, name: str = "Мой вид") -> ActivityCatalogItem:
    item = ActivityCatalogItem(name=name, domains=["journal"], owner_id=user_id)
    db.add(item)
    await db.flush()
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Page + CRUD
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_page_lists_system_and_own(auth_client, test_user, db_session):
    await _system_item(db_session)
    await _own_item(db_session, test_user.id, "Мой вид")
    resp = await auth_client.get("/catalog")
    assert resp.status_code == 200
    assert "Массаж" in resp.text
    assert "Мой вид" in resp.text
    assert "catalog_mine" in resp.text or "mine" in resp.text


@pytest.mark.asyncio
async def test_catalog_page_domain_filter(auth_client, test_user, db_session):
    await _system_item(db_session, "Гигиена")  # domains: journal/care/tracker (no timer)
    await db_session.flush()
    resp = await auth_client.get("/catalog?domain=timer")
    assert resp.status_code == 200
    # Гигиена не применима к timer — не должна попасть в отфильтрованный список
    assert "Гигиена" not in resp.text


@pytest.mark.asyncio
async def test_create_own_item(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/catalog/items",
        data={"name": "Новый вид", "description": "описание", "tags": "a, b", "domains": "journal, care"},
    )
    assert resp.status_code == 303, resp.text
    item = (
        await db_session.execute(select(ActivityCatalogItem).where(ActivityCatalogItem.name == "Новый вид"))
    ).scalar_one()
    assert item.owner_id == test_user.id
    assert item.domains == ["journal", "care"]
    assert item.tags == ["a", "b"]


@pytest.mark.asyncio
async def test_delete_own_item(auth_client, test_user, db_session):
    item = await _own_item(db_session, test_user.id)
    resp = await auth_client.post(f"/catalog/items/{item.id}/delete")
    assert resp.status_code == 303
    assert (
        await db_session.execute(select(ActivityCatalogItem).where(ActivityCatalogItem.id == item.id))
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cannot_delete_system_item(auth_client, test_user, db_session):
    item = await _system_item(db_session)
    resp = await auth_client.post(f"/catalog/items/{item.id}/delete")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_own_item_hidden(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    await _own_item(db_session, other.id, "Чужая запись")
    resp = await auth_client.get("/catalog")
    assert resp.status_code == 200
    assert "Чужая запись" not in resp.text


@pytest.mark.asyncio
async def test_cannot_use_foreign_item_in_journal(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    foreign = await _own_item(db_session, other.id, "Чужой вид")
    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "catalog_item_id": str(foreign.id)},
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Journal integration (replaces free-string activity_type)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_journal_entry_links_catalog_item(auth_client, test_user, db_session):
    item = await _system_item(db_session)
    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "catalog_item_id": str(item.id)},
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    assert entry.catalog_item_id == item.id
    # денормализованный снимок названия для отображения
    assert entry.activity_type == "Массаж"


@pytest.mark.asyncio
async def test_journal_page_has_catalog_picker(auth_client, test_user, db_session):
    await _system_item(db_session)
    resp = await auth_client.get("/journal")
    assert resp.status_code == 200
    assert "catalog_item_id" in resp.text
    assert "Массаж" in resp.text


@pytest.mark.asyncio
async def test_journal_json_links_catalog_item(auth_client, test_user, db_session):
    item = await _system_item(db_session)
    resp = await auth_client.post(
        "/api/v2/journal/entries",
        json={"entry_date": TODAY.isoformat(), "catalog_item_id": str(item.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["catalog_item_id"] == str(item.id)
    assert body["activity_type"] == "Массаж"


# ─────────────────────────────────────────────────────────────────────────────
# Care integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_care_routine_links_catalog_item(auth_client, test_user, db_session):
    item = await _system_item(db_session, "Уход за лицом")
    item.domains = ["care"]
    await db_session.flush()
    resp = await auth_client.post(
        "/care/routines",
        data={"name": "Вечерний уход", "catalog_item_id": str(item.id), "area": "face", "kind": "home"},
    )
    assert resp.status_code == 303, resp.text
    routine = (await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))).scalar_one()
    assert routine.catalog_item_id == item.id


@pytest.mark.asyncio
async def test_care_page_has_catalog_picker(auth_client, test_user, db_session):
    item = await _system_item(db_session, "Уход за лицом")
    item.domains = ["care"]
    await db_session.flush()
    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "catalog_item_id" in resp.text
    assert "Уход за лицом" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Timer integration (window reason/purpose)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slot_rule_links_catalog_item(auth_client, test_user, db_session):
    from app.locktimer.services.drafts import create_draft

    item = await _system_item(db_session, "Гигиена")
    item.domains = ["timer"]
    await db_session.flush()
    session = await create_draft(db_session, owner_id=test_user.id)
    await db_session.flush()
    resp = await auth_client.post(
        f"/api/v2/locktimer/sessions/{session.id}/slot-rules",
        data={
            "name": "Утреннее окно",
            "rule_type": "every_n_days",
            "schedule_json": '{"n":1,"time_of_day":"12:00"}',
            "duration_seconds": "3600",
            "catalog_item_id": str(item.id),
        },
    )
    assert resp.status_code in (200, 303), resp.text
    rule = (await db_session.execute(select(LockSlotRule).where(LockSlotRule.session_id == session.id))).scalar_one()
    assert rule.catalog_item_id == item.id


# ─────────────────────────────────────────────────────────────────────────────
# Tracker integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entity_links_catalog_item(auth_client, test_user, db_session):
    from app.models.entity import Entity

    item = await _system_item(db_session, "Романтика")
    item.domains = ["tracker"]
    await db_session.flush()
    resp = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Свидание",
            "category": "Romance",
            "type": "one_time",
            "catalog_item_id": str(item.id),
        },
    )
    assert resp.status_code == 303, resp.text
    entity = (
        await db_session.execute(select(Entity).where(Entity.owner_id == test_user.id, Entity.real_name == "Свидание"))
    ).scalar_one()
    assert entity.catalog_item_id == item.id


@pytest.mark.asyncio
async def test_my_entities_page_has_catalog_picker(auth_client, test_user, db_session):
    item = await _system_item(db_session, "Романтика")
    item.domains = ["tracker"]
    await db_session.flush()
    resp = await auth_client.get("/entities/my")
    assert resp.status_code == 200
    assert "catalog_item_id" in resp.text
    assert "Романтика" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_list_and_create(auth_client, test_user, db_session):
    await _system_item(db_session)
    resp = await auth_client.get("/api/v2/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(i["name"] == "Массаж" for i in data["items"])

    resp = await auth_client.post(
        "/api/v2/catalog/items",
        json={"name": "JSON вид", "domains": ["journal"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "JSON вид"
    assert resp.json()["owner_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_json_domain_filter(auth_client, test_user, db_session):
    item = await _system_item(db_session, "Гигиена")
    item.domains = ["timer"]
    await db_session.flush()
    resp = await auth_client.get("/api/v2/catalog?domain=timer")
    assert resp.status_code == 200
    assert any(i["name"] == "Гигиена" for i in resp.json()["items"])
    resp = await auth_client.get("/api/v2/catalog?domain=care")
    assert not any(i["name"] == "Гигиена" for i in resp.json()["items"])


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_catalog_module_no_gamification():
    """PD-013: каталог — нейтральный справочник, без игровой интеграции."""
    import inspect

    import app.api.catalog as mod

    source = inspect.getsource(mod)
    assert "app.gamification" not in source
    assert "app.models.points" not in source
    assert "app.models.progress" not in source
    assert "award_points" not in source
    assert "apply_penalty" not in source


# ─────────────────────────────────────────────────────────────────────────────
# JSON DELETE (complete mobile CRUD)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_delete_item(auth_client, test_user, db_session):
    item = (await auth_client.post("/api/v2/catalog/items", json={"name": "JSON вид", "domains": ["journal"]})).json()
    resp = await auth_client.delete(f"/api/v2/catalog/items/{item['id']}")
    assert resp.status_code == 204
    data = (await auth_client.get("/api/v2/catalog")).json()
    assert not any(i["name"] == "JSON вид" for i in data["items"])


@pytest.mark.asyncio
async def test_json_delete_system_item_rejected(auth_client, test_user, db_session):
    item = await _system_item(db_session)
    resp = await auth_client.delete(f"/api/v2/catalog/items/{item.id}")
    assert resp.status_code == 404
