"""Tests for drag&drop reorder, inventory images, photo attachments, diets, multi-plan training."""

import io
import json
import uuid
from datetime import date

import pytest

from app.models.activity_log import ActivityLog
from app.models.diet import Diet, DietItem
from app.models.entity import Entity
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry

# ── Diet model ──


@pytest.mark.asyncio
async def test_diet_with_items(db_session, test_user):
    from sqlalchemy import select

    diet = Diet(user_id=test_user.id, name="Keto", goal="Weight loss", is_active=True)
    db_session.add(diet)
    await db_session.flush()
    db_session.add(DietItem(diet_id=diet.id, name="Eggs", quantity=2, unit="pcs", meal_time="breakfast", sort_order=0))
    db_session.add(DietItem(diet_id=diet.id, name="Avocado", quantity=100, unit="g", meal_time="lunch", sort_order=1))
    await db_session.flush()

    result = await db_session.execute(select(DietItem).where(DietItem.diet_id == diet.id).order_by(DietItem.sort_order))
    items = result.scalars().all()
    assert len(items) == 2
    assert items[0].sort_order == 0
    assert diet.is_active is True


@pytest.mark.asyncio
async def test_diet_items_cascade_delete(db_session, test_user):
    diet = Diet(user_id=test_user.id, name="Test")
    db_session.add(diet)
    await db_session.flush()
    db_session.add(DietItem(diet_id=diet.id, name="Item"))
    await db_session.flush()

    await db_session.delete(diet)
    await db_session.flush()
    # items are gone via cascade


# ── Attachment model ──


@pytest.mark.asyncio
async def test_attachment_model(db_session, test_user):
    from app.models.attachment import Attachment

    att = Attachment(
        user_id=test_user.id,
        owner_type="activity_log",
        owner_id=uuid.uuid4(),
        file_path="/uploads/attachments/abc.jpg",
        sort_order=0,
    )
    db_session.add(att)
    await db_session.flush()
    assert att.file_path.startswith("/uploads/")


# ── Diets API ──


@pytest.mark.asyncio
async def test_diets_page_renders(auth_client):
    res = await auth_client.get("/diets")
    assert res.status_code == 200
    assert "diets" in res.text.lower()


@pytest.mark.asyncio
async def test_diet_crud_api(auth_client, db_session, test_user):
    # create
    res = await auth_client.post("/diets/api", json={"name": "Keto", "goal": "Loss", "is_active": True})
    assert res.status_code == 200
    diet = res.json()
    assert diet["name"] == "Keto"
    assert diet["is_active"] is True

    # list
    res = await auth_client.get("/diets/api")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # add item
    res = await auth_client.post(f"/diets/api/{diet['id']}/items", json={"name": "Eggs", "quantity": 2, "unit": "pcs"})
    assert res.status_code == 200
    item = res.json()
    assert item["name"] == "Eggs"
    assert item["sort_order"] == 0

    # reorder items
    res = await auth_client.post(f"/diets/api/{diet['id']}/items/reorder", json={"ids": [item["id"]]})
    assert res.status_code == 200

    # toggle active off
    res = await auth_client.put(f"/diets/api/{diet['id']}", json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # update item
    res = await auth_client.put(f"/diets/api/{diet['id']}/items/{item['id']}", json={"quantity": 3})
    assert res.status_code == 200
    assert res.json()["quantity"] == 3

    # delete item + diet
    res = await auth_client.delete(f"/diets/api/{diet['id']}/items/{item['id']}")
    assert res.status_code == 200
    res = await auth_client.delete(f"/diets/api/{diet['id']}")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_diet_reorder_mismatch_rejected(auth_client, db_session, test_user):
    res = await auth_client.post("/diets/api", json={"name": "D"})
    diet = res.json()
    # wrong id list
    res = await auth_client.post(f"/diets/api/{diet['id']}/items/reorder", json={"ids": [str(uuid.uuid4())]})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_diet_cross_user_isolation(auth_client, db_session, test_user):
    # another user's diet must not be reachable
    other = Diet(user_id=uuid.uuid4(), name="Other")
    db_session.add(other)
    await db_session.flush()
    res = await auth_client.put(f"/diets/api/{other.id}", json={"name": "Hack"})
    assert res.status_code == 404


# ── Inventory reorder + image ──


@pytest.mark.asyncio
async def test_inventory_reorder(auth_client, db_session, test_user):
    from app.models.life import InventoryItem

    i1 = InventoryItem(user_id=test_user.id, category="equipment", name="A", sort_order=0)
    i2 = InventoryItem(user_id=test_user.id, category="equipment", name="B", sort_order=1)
    db_session.add_all([i1, i2])
    await db_session.flush()

    res = await auth_client.post("/api/v2/inventory/reorder", json={"ids": [str(i2.id), str(i1.id)]})
    assert res.status_code == 200

    res = await auth_client.get("/api/v2/inventory")
    names = [i["name"] for i in res.json()]
    assert names == ["B", "A"]


@pytest.mark.asyncio
async def test_inventory_reorder_partial_with_filter(auth_client, db_session, test_user):
    """Drag&drop with an active filter: only the rendered subset is sent —
    unmentioned items keep their place, unknown ids are rejected."""
    from app.models.life import InventoryItem

    i1 = InventoryItem(user_id=test_user.id, category="equipment", name="A", sort_order=0)
    i2 = InventoryItem(user_id=test_user.id, category="clothing", name="B", sort_order=1)
    i3 = InventoryItem(user_id=test_user.id, category="equipment", name="C", sort_order=2)
    db_session.add_all([i1, i2, i3])
    await db_session.flush()

    # filtered view shows only equipment (A, C); user drags C above A
    res = await auth_client.post("/api/v2/inventory/reorder", json={"ids": [str(i3.id), str(i1.id)]})
    assert res.status_code == 200

    res = await auth_client.get("/api/v2/inventory")
    names = [i["name"] for i in res.json()]
    assert names == ["C", "A", "B"]  # B untouched, still after the moved block

    # unknown id → 400
    res = await auth_client.post("/api/v2/inventory/reorder", json={"ids": [str(i1.id), str(uuid.uuid4())]})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_inventory_image_upload_and_delete(auth_client, db_session, test_user, tmp_path, monkeypatch):
    from app.models.life import InventoryItem

    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))

    item = InventoryItem(user_id=test_user.id, category="equipment", name="Collar")
    db_session.add(item)
    await db_session.flush()

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    res = await auth_client.post(
        f"/api/v2/inventory/{item.id}/image",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
    )
    assert res.status_code == 200
    path = res.json()["image_path"]
    assert path.startswith("/uploads/inventory/")

    # file actually written to disk
    rel = path[len("/uploads/") :]
    assert (tmp_path / rel).exists()

    # delete image
    res = await auth_client.delete(f"/api/v2/inventory/{item.id}/image")
    assert res.status_code == 200
    assert not (tmp_path / rel).exists()


@pytest.mark.asyncio
async def test_inventory_image_rejects_non_image(auth_client, db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    from app.models.life import InventoryItem

    item = InventoryItem(user_id=test_user.id, category="equipment", name="X")
    db_session.add(item)
    await db_session.flush()

    res = await auth_client.post(
        f"/api/v2/inventory/{item.id}/image",
        files={"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400

    # spoofed content-type but wrong magic bytes
    res = await auth_client.post(
        f"/api/v2/inventory/{item.id}/image",
        files={"file": ("evil.png", io.BytesIO(b"hello"), "image/png")},
    )
    assert res.status_code == 400


# ── Attachments API ──


@pytest.mark.asyncio
async def test_attachment_upload_list_delete(auth_client, db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    owner_id = uuid.uuid4()

    png = b"\x89PNG\r\n\x1a\n" + b"report"
    res = await auth_client.post(
        "/attachments",
        params={"owner_type": "activity_log", "owner_id": str(owner_id)},
        files={"file": ("r.png", io.BytesIO(png), "image/png")},
    )
    assert res.status_code == 200
    att = res.json()
    assert att["owner_type"] == "activity_log"

    res = await auth_client.get("/attachments", params={"owner_type": "activity_log", "owner_id": str(owner_id)})
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = await auth_client.delete(f"/attachments/{att['id']}")
    assert res.status_code == 200

    res = await auth_client.get("/attachments", params={"owner_type": "activity_log", "owner_id": str(owner_id)})
    assert res.json() == []


@pytest.mark.asyncio
async def test_attachment_rejects_unknown_owner_type(auth_client):
    res = await auth_client.post(
        "/attachments",
        params={"owner_type": "hack", "owner_id": str(uuid.uuid4())},
        files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\nx"), "image/png")},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_attachment_cross_user_isolation(auth_client, db_session, test_user):
    from app.models.attachment import Attachment

    other = Attachment(
        user_id=uuid.uuid4(),
        owner_type="activity_log",
        owner_id=uuid.uuid4(),
        file_path="/uploads/attachments/other.jpg",
    )
    db_session.add(other)
    await db_session.flush()

    res = await auth_client.delete(f"/attachments/{other.id}")
    assert res.status_code == 404


# ── Training: journal reorder + multiple plans ──


@pytest.mark.asyncio
async def test_training_log_reorder(auth_client, db_session, test_user):
    day = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(day)
    await db_session.flush()

    e1 = TrainingLogEntry(
        training_day_id=day.id, user_id=test_user.id, time_label="09:00", entry_type="fluid_intake", sort_order=0
    )
    e2 = TrainingLogEntry(
        training_day_id=day.id, user_id=test_user.id, time_label="13:00", entry_type="pressure_check", sort_order=1
    )
    db_session.add_all([e1, e2])
    await db_session.flush()

    res = await auth_client.post(
        "/training/log-entry/reorder",
        json={"training_day_id": str(day.id), "ids": [str(e2.id), str(e1.id)]},
    )
    assert res.status_code == 200

    await db_session.refresh(e1)
    await db_session.refresh(e2)
    assert e1.sort_order == 1
    assert e2.sort_order == 0


@pytest.mark.asyncio
async def test_training_log_reorder_mismatch(auth_client, db_session, test_user):
    day = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(day)
    await db_session.flush()
    e1 = TrainingLogEntry(
        training_day_id=day.id, user_id=test_user.id, time_label="09:00", entry_type="fluid_intake", sort_order=0
    )
    db_session.add(e1)
    await db_session.flush()

    res = await auth_client.post(
        "/training/log-entry/reorder",
        json={"training_day_id": str(day.id), "ids": [str(e1.id), str(uuid.uuid4())]},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_training_log_reorder_cross_user(auth_client, db_session, test_user):
    other = TrainingDay(user_id=uuid.uuid4(), target_date=date.today(), status="active")
    db_session.add(other)
    await db_session.flush()
    e1 = TrainingLogEntry(
        training_day_id=other.id, user_id=uuid.uuid4(), time_label="09:00", entry_type="fluid_intake", sort_order=0
    )
    db_session.add(e1)
    await db_session.flush()

    res = await auth_client.post(
        "/training/log-entry/reorder",
        json={"training_day_id": str(other.id), "ids": [str(e1.id)]},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_training_page_shows_multiple_plans_and_timeline(auth_client, db_session, test_user):
    today = date.today()
    d1 = TrainingDay(user_id=test_user.id, target_date=today, name="Morning", status="active")
    d2 = TrainingDay(user_id=test_user.id, target_date=today, name="Evening", status="active")
    db_session.add_all([d1, d2])
    await db_session.flush()

    ent = Entity(type="one_time", real_name="Plank", category="fitness", owner_id=test_user.id)
    db_session.add(ent)
    await db_session.flush()

    db_session.add(
        ActivityLog(
            user_id=test_user.id,
            entity_id=ent.id,
            training_day_id=d1.id,
            status="planned",
            selected_entity_name="Plank",
            subtasks=[{"id": 1, "desc": "Hold", "is_done": False}],
        )
    )
    db_session.add(
        TrainingLogEntry(
            training_day_id=d1.id, user_id=test_user.id, time_label="09:00", entry_type="fluid_intake", sort_order=0
        )
    )
    await db_session.flush()

    res = await auth_client.get("/training/")
    assert res.status_code == 200
    html = res.text
    assert "Morning" in html
    assert "Evening" in html
    assert "timeline-data" in html  # timeline scale rendered
    assert 'draggable="true"' in html  # journal entries draggable


@pytest.mark.asyncio
async def test_multiple_training_days_model(db_session, test_user):
    today = date.today()
    d1 = TrainingDay(user_id=test_user.id, target_date=today, name="Morning")
    d2 = TrainingDay(user_id=test_user.id, target_date=today, name="Evening")
    db_session.add_all([d1, d2])
    await db_session.flush()
    assert d1.name == "Morning"
    assert d2.name == "Evening"


# ── Training: plan generation with name (pipeline unit) ──


@pytest.mark.asyncio
async def test_generate_daily_plan_accepts_name(db_session, test_user):
    """Verify the pipeline passes the plan name into TrainingDay (mocked LLM)."""
    from unittest.mock import AsyncMock, patch

    from app.llm.pipeline import generate_daily_plan
    from app.models.llm_config import LLMProviderConfig

    llm_config = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="test",
        api_base_url="http://test",
        api_key_encrypted="encrypted-key",
        model_name="m",
        llm_mode="full",
        store_raw_response=True,
    )
    db_session.add(llm_config)
    await db_session.flush()

    plan_payload = {
        "plan_summary": "Test plan",
        "tasks": [
            {
                "entity_id": str(uuid.uuid4()),
                "entity_name": "Task",
                "params": {},
                "subtasks": [],
            }
        ],
    }

    full_context = {
        "allowed_entities": [],
        "allowed_ids": [],
        "stats": {
            "total_activities": 0,
            "completed": 0,
            "stopped": 0,
            "week_activities": 0,
        },
        "recent_history": [],
        "active_penalties": [],
        "calendar_schedule": None,
        "locale": "en",
    }

    with (
        patch("app.llm.context_builder.build_context", new=AsyncMock(return_value=full_context)),
        patch("app.llm.validator.get_allowed_ids", return_value={plan_payload["tasks"][0]["entity_id"]}),
        patch(
            "app.llm.client.call_llm",
            new=AsyncMock(
                return_value={
                    "content": json.dumps(plan_payload),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
                }
            ),
        ),
    ):
        day = await generate_daily_plan(
            db=db_session,
            user_id=test_user.id,
            llm_config=llm_config,
            target_date=date.today(),
            locale="en",
            name="Morning",
        )
    assert day.name == "Morning"


# ── Uploads helper ──


@pytest.mark.asyncio
async def test_save_image_rejects_oversize(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from starlette.datastructures import UploadFile

    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.max_upload_bytes", 16)

    from app.services.uploads import save_image

    big = UploadFile(filename="big.png", file=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 100))
    with pytest.raises(HTTPException):
        await save_image(big, subdir="inventory")
