import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.models.user import User


@pytest.mark.asyncio
async def test_personalize_creates_fork_entity(
    auth_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession,
):
    # 1. Create a public base entity template
    base_entity = Entity(
        real_name="Базовая планка",
        category="Фитнес",
        type="one_time",
        is_public=True,
        params_schema={"duration_min": {"min": 5, "max": 15}},
    )
    db_session.add(base_entity)
    await db_session.flush()

    # 2. Call personalize endpoint as test_user
    resp = await auth_client.post(
        f"/entities/{base_entity.id}/personalize",
        data={
            "custom_name": "Моя персональная планка",
            "duration_min": 10,
            "duration_max": 25,
            "reps_min": 3,
            "reps_max": 5,
            "desire_level": "want_very_much",
            "is_opted_in": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # 3. Verify fork entity was created
    fork_res = await db_session.execute(
        select(Entity).where(Entity.owner_id == test_user.id, Entity.parent_id == base_entity.id)
    )
    fork = fork_res.scalar_one_or_none()
    assert fork is not None
    assert fork.real_name == "Моя персональная планка"
    assert fork.is_public is False
    assert fork.params_schema["duration_min"]["min"] == 10
    assert fork.params_schema["duration_min"]["max"] == 25
    assert fork.params_schema["reps"]["min"] == 3
    assert fork.params_schema["reps"]["max"] == 5

    # 4. Verify opt-in was recorded for the fork
    oi_res = await db_session.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == test_user.id,
            UserEntityOptIn.entity_id == fork.id,
        )
    )
    opt_in = oi_res.scalar_one_or_none()
    assert opt_in is not None
    assert opt_in.desire_level == "want_very_much"
    assert opt_in.is_opted_in is True


@pytest.mark.asyncio
async def test_personalize_stores_inventory_ids(
    auth_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession,
):
    """R2.5: assigned_inventory_ids → typed inventory_selector param (ADR-041)."""
    base_entity = Entity(
        real_name="База с инвентарём",
        category="Фитнес",
        type="one_time",
        is_public=True,
        params_schema={"reps": {"min": 5, "max": 10}},
    )
    db_session.add(base_entity)
    await db_session.flush()

    resp = await auth_client.post(
        f"/entities/{base_entity.id}/personalize",
        data={
            "duration_min": "30",
            "duration_max": "120",
            "assigned_inventory_ids": "inv-a,inv-b",
            "assigned_care_ids": "care-1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    fork_res = await db_session.execute(
        select(Entity).where(Entity.owner_id == test_user.id, Entity.parent_id == base_entity.id)
    )
    fork = fork_res.scalar_one_or_none()
    assert fork is not None
    inv = fork.params_schema.get("inventory_ids")
    assert inv == {
        "type": "inventory_selector",
        "title": "Inventory",
        "selection_mode": "multiple",
        "required": False,
        "value": ["inv-a", "inv-b"],
    }
    assert fork.care_product_ids == ["care-1"]
    # duration persisted as seconds into the fork schema
    assert fork.params_schema["duration_min"]["min"] == 30
    assert fork.params_schema["duration_min"]["max"] == 120


@pytest.mark.asyncio
async def test_catalog_page_renders_personalize_modal(
    auth_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession,
):
    """R2.5: catalog card shows «Настроить» button + modal with pickers, no raw JSON."""
    base_entity = Entity(
        real_name="Карточка с параметрами",
        category="Фитнес",
        type="one_time",
        is_public=True,
        params_schema={"duration_minutes": {"min": 3, "max": 20, "unit": "minutes"}},
    )
    db_session.add(base_entity)
    await db_session.flush()

    resp = await auth_client.get("/entities/catalog")
    assert resp.status_code == 200
    html = resp.text
    # modal present
    assert 'id="personalize-modal"' in html
    assert 'openPersonalizeModal(this)' in html
    assert "duration-picker" in html
    assert "quantity-picker" in html
    # data attrs prefill (3–20 minutes → 180–1200 seconds)
    assert 'data-dur-min="180"' in html
    assert 'data-dur-max="1200"' in html
    # human-readable chips instead of raw JSON
    assert "<pre>" not in html or "params_schema" not in html.split("<pre>")[1][:50]
    assert "3–20 min" in html


@pytest.mark.asyncio
async def test_catalog_modal_renders_inventory_and_care_selectors(
    auth_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession,
):
    """R2.5: with care products + inventory present, modal shows checkbox groups."""
    try:
        from app.models.care import CareProduct
        from app.models.life import InventoryItem

        db_session.add(
            CareProduct(user_id=test_user.id, name="Бальзам", category="care")
        )
        db_session.add(
            InventoryItem(user_id=test_user.id, name="Кнут", category="impact_tool")
        )
        await db_session.flush()
    except Exception:
        pytest.skip("care/inventory models unavailable")

    ent = Entity(real_name="С инвентарём", category="Фитнес", type="one_time", is_public=True)
    db_session.add(ent)
    await db_session.flush()

    resp = await auth_client.get("/entities/catalog")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="pd-inv-cb' in html
    assert 'class="pd-care-cb' in html
    assert '>Кнут</span>' in html
    assert 'Бальзам' in html
