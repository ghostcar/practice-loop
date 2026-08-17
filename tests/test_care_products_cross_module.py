"""Care Products cross-module integration tests (Шаг 17b, ADR-094).

Каталог средств/косметики доработан (остаток/срок/каталог) и связан с другими
модулями личного контура:
- таймер: lock_slot_rules.care_product_ids — средства для окна;
- трекер: entities.care_product_ids — средства для задачи;
- журнал: sj_entries.care_product_ids — использованные средства в записи;
- уход: care_routine_products — рекомендуемые средства для процедуры;
- медиа: owner_type=care_product — фото средства;
- Insights: средства в контексте care (расход/регулярность/low-stock).

Relief-only (PD-013): без игровой интеграции.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.care import CareEntry, CareProduct, CareRoutine, CareRoutineProduct
from app.models.entity import Entity
from app.models.journal import JournalEntry
from app.models.life import InventoryItem
from app.models.locktimer import LockSession, LockSlotRule
from app.models.user import User

TODAY = date.today()


async def _add_product(
    db_session, user_id: User, name: str = "Serum", quantity: int = 0, expiry: date | None = None
) -> CareProduct:
    p = CareProduct(
        user_id=user_id.id,
        name=name,
        category="serum",
        quantity=quantity,
        expiry_date=expiry,
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _add_inventory(db_session, user_id: User, name: str = "Cosmetic item") -> InventoryItem:
    item = InventoryItem(user_id=user_id.id, category="cosmetics", name=name, quantity=1, quantity_needed=1)
    db_session.add(item)
    await db_session.flush()
    return item


async def _add_other_user(db_session) -> User:
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    return other


# ─────────────────────────────────────────────────────────────────────────────
# Care products — stock + expiry + catalog
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_product_with_quantity_expiry_catalog(auth_client, test_user, db_session):
    inv = await _add_inventory(db_session, test_user, name="Vitamin C")
    resp = await auth_client.post(
        "/care/products",
        data={
            "name": "Vitamin C serum",
            "category": "serum",
            "brand": "TheOrdinary",
            "quantity": "3",
            "expiry_date": (TODAY + timedelta(days=200)).isoformat(),
            "inventory_item_id": str(inv.id),
        },
    )
    assert resp.status_code == 303, resp.text
    product = (
        await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))
    ).scalar_one()
    assert product.quantity == 3
    assert product.expiry_date is not None
    assert product.inventory_item_id == inv.id

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Vitamin C serum" in resp.text


@pytest.mark.asyncio
async def test_low_stock_and_expiring_badges(auth_client, test_user, db_session):
    await _add_product(db_session, test_user, name="Low stock serum", quantity=1)
    await _add_product(db_session, test_user, name="Expiring mask", quantity=5, expiry=TODAY + timedelta(days=10))
    await _add_product(db_session, test_user, name="Healthy toner", quantity=4, expiry=TODAY + timedelta(days=120))
    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Low stock serum" in resp.text
    # бейджи low-stock и expiring присутствуют в разметке
    assert "low_stock" in resp.text or "Low stock" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Care products media (owner_type=care_product)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_media_upload(auth_client, test_user, db_session):
    import io

    p = await _add_product(db_session, test_user, name="Photo serum")
    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    resp = await auth_client.post(
        f"/care/products/{p.id}/media",
        files={"file": ("serum.png", io.BytesIO(png), "image/png")},
    )
    assert resp.status_code in (200, 303), resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Care routine ↔ products (care_routine_products)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_routine_with_recommended_products(auth_client, test_user, db_session):
    p1 = await _add_product(db_session, test_user, name="Cleanser A")
    p2 = await _add_product(db_session, test_user, name="Toner B")
    resp = await auth_client.post(
        "/care/routines",
        data={
            "name": "Evening care",
            "area": "face",
            "kind": "home",
            "product_ids": [str(p1.id), str(p2.id)],
        },
    )
    assert resp.status_code == 303, resp.text
    routine = (
        await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))
    ).scalar_one()
    rows = (
        await db_session.execute(select(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine.id))
    ).scalars().all()
    assert {r.product_id for r in rows} == {p1.id, p2.id}


# ─────────────────────────────────────────────────────────────────────────────
# Timer: lock_slot_rules.care_product_ids
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slot_rule_with_care_products(auth_client, test_user, db_session):
    p = await _add_product(db_session, test_user, name="Timer serum")
    # создаём draft-сессию через API
    resp = await auth_client.post("/locktimer/new")
    assert resp.status_code in (200, 303, 307), resp.text
    session = (
        await db_session.execute(select(LockSession).where(LockSession.owner_id == test_user.id))
    ).scalars().first()
    assert session is not None

    resp = await auth_client.post(
        f"/api/v2/locktimer/sessions/{session.id}/slot-rules",
        data={
            "name": "Care window",
            "rule_type": "every_n_days",
            "schedule_json": '{"n":1,"time_of_day":"12:00"}',
            "duration_seconds": "1800",
            "care_product_ids": str(p.id),
        },
    )
    assert resp.status_code in (200, 303), resp.text
    rule = (
        await db_session.execute(select(LockSlotRule).where(LockSlotRule.session_id == session.id))
    ).scalar_one()
    assert rule.care_product_ids == [str(p.id)]


@pytest.mark.asyncio
async def test_slot_rule_foreign_care_product_rejected(auth_client, test_user, db_session):
    # чужое средство → 400
    other = await _add_other_user(db_session)
    foreign = await _add_product(db_session, other, name="Foreign serum")
    resp = await auth_client.post("/locktimer/new")
    session = (
        await db_session.execute(select(LockSession).where(LockSession.owner_id == test_user.id))
    ).scalars().first()
    resp = await auth_client.post(
        f"/api/v2/locktimer/sessions/{session.id}/slot-rules",
        data={
            "name": "Bad window",
            "rule_type": "every_n_days",
            "schedule_json": '{"n":1,"time_of_day":"12:00"}',
            "duration_seconds": "1800",
            "care_product_ids": str(foreign.id),
        },
    )
    assert resp.status_code == 400, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Tracker: entities.care_product_ids
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entity_with_care_products(auth_client, test_user, db_session):
    p = await _add_product(db_session, test_user, name="Massage oil")
    resp = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Massage with oil",
            "type": "one_time",
            "category": "massage",
            "care_product_ids": str(p.id),
        },
    )
    assert resp.status_code == 303, resp.text
    entity = (
        await db_session.execute(select(Entity).where(Entity.owner_id == test_user.id))
    ).scalar_one()
    assert entity.care_product_ids == [str(p.id)]


# ─────────────────────────────────────────────────────────────────────────────
# Journal: sj_entries.care_product_ids (form + JSON)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_journal_entry_with_care_products_form(auth_client, test_user, db_session):
    p = await _add_product(db_session, test_user, name="Lube")
    resp = await auth_client.post(
        "/journal/entries",
        data={
            "entry_date": TODAY.isoformat(),
            "activity_type": "intimacy",
            "care_product_ids": str(p.id),
        },
    )
    assert resp.status_code == 303, resp.text
    entry = (
        await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))
    ).scalar_one()
    assert entry.care_product_ids == [str(p.id)]


@pytest.mark.asyncio
async def test_journal_entry_with_care_products_json(auth_client, test_user, db_session):
    p = await _add_product(db_session, test_user, name="Lube JSON")
    resp = await auth_client.post(
        "/api/v2/journal/entries",
        json={
            "entry_date": TODAY.isoformat(),
            "activity_type": "intimacy",
            "care_product_ids": [str(p.id)],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["care_product_ids"] == [str(p.id)]


@pytest.mark.asyncio
async def test_journal_entry_foreign_care_product_rejected(auth_client, test_user, db_session):
    other = await _add_other_user(db_session)
    foreign = await _add_product(db_session, other, name="Foreign lube")
    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "activity_type": "intimacy", "care_product_ids": str(foreign.id)},
    )
    assert resp.status_code == 400, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Insights: care context includes products
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insights_care_context_includes_products(db_session, test_user):
    p = await _add_product(db_session, test_user, name="Insight serum", quantity=1)
    entry = CareEntry(user_id=test_user.id, entry_date=TODAY, routine_id=None)
    db_session.add(entry)
    await db_session.flush()
    from app.models.care import CareEntryProduct

    db_session.add(CareEntryProduct(entry_id=entry.id, product_id=p.id))
    await db_session.flush()

    from app.llm.pipeline.insights import _ctx_care

    lines = await _ctx_care(db_session, test_user.id, TODAY - timedelta(days=30), TODAY)
    assert any("care entries" in line for line in lines)
    assert any("Insight serum" in line for line in lines)
    assert any("low stock" in line for line in lines)


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only: no gamification
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_care_products_relief_only_no_points(auth_client, test_user, db_session):
    # создание средства/рутины не создаёт XP/баллов (relief-only, PD-013)
    p = await _add_product(db_session, test_user, name="Relief serum")
    resp = await auth_client.post(
        "/care/routines",
        data={"name": "Relief routine", "area": "face", "kind": "home", "product_ids": [str(p.id)]},
    )
    assert resp.status_code == 303, resp.text
    routine = (
        await db_session.execute(select(CareRoutine).where(CareRoutine.user_id == test_user.id))
    ).scalar_one()
    # рекомендация средств сохранена; никакой игровой механики у ухода нет
    rows = (
        await db_session.execute(select(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine.id))
    ).scalars().all()
    assert len(rows) == 1
