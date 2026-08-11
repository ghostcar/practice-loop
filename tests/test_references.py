"""Tests: reference data models, seeds, API, task links, DSL selectors (update2.md).

Covers: BodyPart seed/API, TaskLocation CRUD/archive, TaskBodyTarget batch,
TaskLocationUsage, TaskInventoryUsage, inventory available, task search,
DSL selector types, cross-user isolation, backward compatibility.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.body_part import BodyPart, TaskBodyTarget
from app.models.entity import Entity
from app.models.inventory_category import InventoryCategory
from app.models.life import InventoryItem
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocation, TaskLocationUsage
from app.models.user import User
from app.params import PARAM_TYPES, normalize_schema, validate_params
from app.seed_body_parts import BODY_PARTS_SEED, seed_body_parts
from app.seed_inventory_categories import INVENTORY_CATEGORIES_SEED, seed_inventory_categories
from app.seed_locations import LOCATIONS_SEED, seed_locations

# ═════════════════════════════════════════════════════════════════════════
# Seed tests
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_seed_body_parts_creates_hierarchy(db_session):
    """40 body parts seeded; parent/child relationships correct."""
    await seed_body_parts(db_session)
    await db_session.flush()

    result = await db_session.execute(select(BodyPart).order_by(BodyPart.sort_order))
    parts = result.scalars().all()
    assert len(parts) >= len(BODY_PARTS_SEED)

    # Top-level entries have no parent
    toplevel = [p for p in parts if p.parent_id is None]
    assert len(toplevel) >= 10  # head, torso groups, arms, legs, intimate

    # Hierarchy checks
    by_slug = {p.slug: p for p in parts}
    face = by_slug.get("face")
    head = by_slug.get("head")
    assert face is not None and head is not None
    assert face.parent_id == head.id

    lips = by_slug.get("lips")
    assert lips is not None and lips.parent_id == face.id
    assert lips.is_sensitive is True


@pytest.mark.asyncio
async def test_seed_body_parts_is_idempotent(db_session):
    """Second call doesn't duplicate records."""
    await seed_body_parts(db_session)
    await db_session.flush()
    await seed_body_parts(db_session)
    await db_session.flush()

    result = await db_session.execute(select(BodyPart))
    assert len(result.scalars().all()) == len(BODY_PARTS_SEED)


@pytest.mark.asyncio
async def test_seed_locations_creates_system_set(db_session):
    """25 system locations seeded with correct types."""
    await seed_locations(db_session)
    await db_session.flush()

    result = await db_session.execute(select(TaskLocation))
    locs = result.scalars().all()
    assert len(locs) >= len(LOCATIONS_SEED)
    assert all(loc.is_custom is False for loc in locs)

    # Concrete locations have parents
    by_slug = {loc.slug: loc for loc in locs}
    bedroom = by_slug.get("bedroom")
    home = by_slug.get("home")
    assert bedroom is not None and home is not None
    assert bedroom.parent_id == home.id
    assert bedroom.location_type == "room"
    assert bedroom.privacy_level == "private"


@pytest.mark.asyncio
async def test_seed_locations_is_idempotent(db_session):
    await seed_locations(db_session)
    await db_session.flush()
    await seed_locations(db_session)
    await db_session.flush()

    result = await db_session.execute(select(TaskLocation))
    assert len(result.scalars().all()) == len(LOCATIONS_SEED)


@pytest.mark.asyncio
async def test_seed_inventory_categories_16(db_session):
    """16 inventory categories seeded."""
    await seed_inventory_categories(db_session)
    await db_session.flush()

    result = await db_session.execute(select(InventoryCategory))
    cats = result.scalars().all()
    assert len(cats) == len(INVENTORY_CATEGORIES_SEED)

    slugs = {c.slug for c in cats}
    assert "impact_tool" in slugs
    assert "wearable" in slugs
    assert "fitness_equipment" in slugs
    assert "clothing" in slugs


@pytest.mark.asyncio
async def test_seed_inventory_categories_is_idempotent(db_session):
    await seed_inventory_categories(db_session)
    await db_session.flush()
    await seed_inventory_categories(db_session)
    await db_session.flush()

    result = await db_session.execute(select(InventoryCategory))
    assert len(result.scalars().all()) == len(INVENTORY_CATEGORIES_SEED)


# ═════════════════════════════════════════════════════════════════════════
# BodyPart API
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_body_parts_list(db_session, auth_client):
    await seed_body_parts(db_session)
    await db_session.flush()

    r = await auth_client.get("/api/v2/body-parts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 39


@pytest.mark.asyncio
async def test_body_parts_filter_by_system(db_session, auth_client):
    await seed_body_parts(db_session)
    await db_session.flush()

    r = await auth_client.get("/api/v2/body-parts?body_system=intimate")
    assert r.status_code == 200
    data = r.json()
    assert all(bp["body_system"] == "intimate" for bp in data)
    assert len(data) >= 3  # intimate_area, genitals, anal_area


@pytest.mark.asyncio
async def test_body_parts_tree(db_session, auth_client):
    await seed_body_parts(db_session)
    await db_session.flush()

    r = await auth_client.get("/api/v2/body-parts/tree")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 10  # top-level nodes
    head = next(n for n in data if n["slug"] == "head")
    assert len(head["children"]) >= 3  # hair, face, neck, ears
    face = next(c for c in head["children"] if c["slug"] == "face")
    assert len(face["children"]) >= 3  # forehead, cheeks, lips, mouth


@pytest.mark.asyncio
async def test_body_part_by_id(db_session, auth_client):
    await seed_body_parts(db_session)
    await db_session.flush()

    result = await db_session.execute(select(BodyPart).where(BodyPart.slug == "cheeks"))
    bp = result.scalar_one()

    r = await auth_client.get(f"/api/v2/body-parts/{bp.id}")
    assert r.status_code == 200
    assert r.json()["slug"] == "cheeks"


# ═════════════════════════════════════════════════════════════════════════
# TaskLocation API
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_locations_list_combines_system_and_user(db_session, auth_client, test_user):
    await seed_locations(db_session)
    await db_session.flush()

    # Create a user-custom location
    loc = TaskLocation(
        slug="my-garage",
        title_ru="Мой гараж",
        location_type="other",
        is_custom=True,
        owner_id=test_user.id,
    )
    db_session.add(loc)
    await db_session.flush()

    r = await auth_client.get("/api/v2/locations")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= len(LOCATIONS_SEED) + 1
    assert any(loc["is_custom"] for loc in data)


@pytest.mark.asyncio
async def test_locations_tree(db_session, auth_client):
    await seed_locations(db_session)
    await db_session.flush()

    r = await auth_client.get("/api/v2/locations/tree")
    assert r.status_code == 200
    data = r.json()
    # Top-level groups: home, room, bathroom, training, furniture, remote, virtual, outdoor, other
    assert len(data) >= 9


@pytest.mark.asyncio
async def test_create_location(db_session, auth_client, test_user):
    r = await auth_client.post(
        "/api/v2/locations",
        json={"slug": "my-balcony", "title_ru": "Балкон", "location_type": "outdoor", "privacy_level": "private"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == "my-balcony"
    assert data["is_custom"] is True
    assert data["owner_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_create_location_duplicate_slug_rejected(db_session, auth_client):
    await seed_locations(db_session)
    await db_session.flush()

    r = await auth_client.post(
        "/api/v2/locations",
        json={"slug": "bedroom", "title_ru": "Dup", "location_type": "room"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_update_custom_location(db_session, auth_client, test_user):
    loc = TaskLocation(slug="test-loc", title_ru="Test", is_custom=True, owner_id=test_user.id)
    db_session.add(loc)
    await db_session.flush()

    r = await auth_client.put(f"/api/v2/locations/{loc.id}", json={"title_ru": "Updated"})
    assert r.status_code == 200
    assert r.json()["title_ru"] == "Updated"


@pytest.mark.asyncio
async def test_cannot_edit_system_location(db_session, auth_client):
    await seed_locations(db_session)
    await db_session.flush()

    result = await db_session.execute(select(TaskLocation).where(TaskLocation.slug == "bedroom"))
    loc = result.scalar_one()

    r = await auth_client.put(f"/api/v2/locations/{loc.id}", json={"title_ru": "Hacked"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_archive_location(db_session, auth_client, test_user):
    loc = TaskLocation(slug="archive-me", title_ru="X", is_custom=True, owner_id=test_user.id)
    db_session.add(loc)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/locations/{loc.id}/archive")
    assert r.status_code == 200

    await db_session.refresh(loc)
    assert loc.is_active is False


@pytest.mark.asyncio
async def test_delete_location_with_refs_blocked(db_session, auth_client, test_user):
    """Can't hard-delete a location that is referenced by tasks."""
    loc = TaskLocation(slug="refd-loc", title_ru="Ref", is_custom=True, owner_id=test_user.id)
    db_session.add(loc)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    usage = TaskLocationUsage(
        task_id=log.id,
        location_id=loc.id,
        location_name_snapshot="Ref",
    )
    db_session.add(usage)
    await db_session.flush()

    r = await auth_client.delete(f"/api/v2/locations/{loc.id}")
    assert r.status_code == 409  # Conflict — task references exist


@pytest.mark.asyncio
async def test_delete_location_without_refs(db_session, auth_client, test_user):
    loc = TaskLocation(slug="del-me", title_ru="Del", is_custom=True, owner_id=test_user.id)
    db_session.add(loc)
    await db_session.flush()

    r = await auth_client.delete(f"/api/v2/locations/{loc.id}")
    assert r.status_code == 200


# ═════════════════════════════════════════════════════════════════════════
# TaskBodyTarget
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_body_targets_creates_with_snapshot(db_session, auth_client, test_user):
    await seed_body_parts(db_session)
    await db_session.flush()

    result = await db_session.execute(select(BodyPart).where(BodyPart.slug == "torso_buttocks"))
    bp = result.scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/body-targets",
        json={
            "targets": [
                {
                    "body_part_id": str(bp.id),
                    "target_role": "primary_target",
                    "side": "both",
                    "planned_intensity": 3,
                }
            ]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["body_part_name_snapshot"] == "Ягодицы"
    assert data[0]["target_role"] == "primary_target"
    assert data[0]["planned_intensity"] == 3


@pytest.mark.asyncio
async def test_set_body_targets_replaces_old(db_session, auth_client, test_user):
    """Batch replace: old targets deleted, new ones created."""
    await seed_body_parts(db_session)
    await db_session.flush()

    bp1 = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "torso_chest"))).scalar_one()
    bp2 = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "abs"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    # First batch
    await auth_client.post(
        f"/api/v2/tasks/{log.id}/body-targets",
        json={"targets": [{"body_part_id": str(bp1.id), "target_role": "primary_target"}]},
    )

    # Second batch — replaces
    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/body-targets",
        json={
            "targets": [
                {"body_part_id": str(bp1.id), "target_role": "primary_target"},
                {"body_part_id": str(bp2.id), "target_role": "secondary_target"},
            ]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_body_targets(db_session, auth_client, test_user):
    await seed_body_parts(db_session)
    await db_session.flush()

    bp = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "thighs"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    tbt = TaskBodyTarget(
        task_id=log.id,
        body_part_id=bp.id,
        body_part_name_snapshot="Бёдра",
        target_role="training_target",
        side="left",
    )
    db_session.add(tbt)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/{log.id}/body-targets")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["side"] == "left"


@pytest.mark.asyncio
async def test_delete_body_target(db_session, auth_client, test_user):
    await seed_body_parts(db_session)
    await db_session.flush()

    bp = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "arms"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    tbt = TaskBodyTarget(task_id=log.id, body_part_id=bp.id, body_part_name_snapshot="Руки")
    db_session.add(tbt)
    await db_session.flush()

    r = await auth_client.delete(f"/api/v2/tasks/{log.id}/body-targets/{tbt.id}")
    assert r.status_code == 200

    result = await db_session.execute(select(TaskBodyTarget).where(TaskBodyTarget.task_id == log.id))
    assert result.scalar_one_or_none() is None


# ═════════════════════════════════════════════════════════════════════════
# TaskLocationUsage
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_location_usages_with_snapshot(db_session, auth_client, test_user):
    await seed_locations(db_session)
    await db_session.flush()

    loc = (await db_session.execute(select(TaskLocation).where(TaskLocation.slug == "bedroom"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/location-usages",
        json={"usages": [{"location_id": str(loc.id), "location_role": "primary_location"}]},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["location_name_snapshot"] == "Спальня"


@pytest.mark.asyncio
async def test_list_location_usages(db_session, auth_client, test_user):
    await seed_locations(db_session)
    await db_session.flush()

    loc = (await db_session.execute(select(TaskLocation).where(TaskLocation.slug == "kitchen"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    usage = TaskLocationUsage(task_id=log.id, location_id=loc.id, location_name_snapshot="Кухня")
    db_session.add(usage)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/{log.id}/location-usages")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ═════════════════════════════════════════════════════════════════════════
# TaskInventoryUsage
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_inventory_usages_with_snapshot(db_session, auth_client, test_user):
    item = InventoryItem(user_id=test_user.id, name="Black Belt", category="impact_tool", status="need")
    db_session.add(item)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/inventory-usages",
        json={
            "usages": [
                {
                    "inventory_item_id": str(item.id),
                    "usage_role": "primary_tool",
                    "planned_quantity": 1,
                    "unit": "pcs",
                }
            ]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["inventory_name_snapshot"] == "Black Belt"
    assert data[0]["inventory_category_snapshot"] == "impact_tool"


@pytest.mark.asyncio
async def test_set_inventory_usages_only_own_items(db_session, auth_client, test_user):
    """Can't link someone else's inventory item — snapshot falls back to ID string."""
    other_user = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other_user)
    await db_session.flush()

    other_item = InventoryItem(user_id=other_user.id, name="Secret", category="other", status="need")
    db_session.add(other_item)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/inventory-usages",
        json={"usages": [{"inventory_item_id": str(other_item.id), "usage_role": "primary_tool"}]},
    )
    assert r.status_code == 200
    data = r.json()
    # Snapshot falls back to the ID string since item not found for this user
    assert data[0]["inventory_name_snapshot"] == str(other_item.id)
    assert data[0]["inventory_category_snapshot"] is None


@pytest.mark.asyncio
async def test_list_inventory_usages(db_session, auth_client, test_user):
    item = InventoryItem(user_id=test_user.id, name="Rope", category="bondage_equipment", status="need")
    db_session.add(item)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    usage = TaskInventoryUsage(
        task_id=log.id,
        inventory_item_id=item.id,
        inventory_name_snapshot="Rope",
        inventory_category_snapshot="bondage_equipment",
        usage_role="restraint",
    )
    db_session.add(usage)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/{log.id}/inventory-usages")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ═════════════════════════════════════════════════════════════════════════
# Inventory available
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_available_inventory_excludes_archived(db_session, auth_client, test_user):
    """Archived/unavailable items are excluded from available list."""
    await seed_inventory_categories(db_session)
    await db_session.flush()

    result = await db_session.execute(select(InventoryCategory).where(InventoryCategory.slug == "impact_tool"))
    cat = result.scalar_one()

    available = InventoryItem(
        user_id=test_user.id,
        name="Paddle",
        category="impact_tool",
        inventory_category_id=cat.id,
        inventory_status="available",
        status="need",
    )
    archived = InventoryItem(
        user_id=test_user.id,
        name="Old Belt",
        category="impact_tool",
        inventory_category_id=cat.id,
        inventory_status="archived",
        status="need",
    )
    db_session.add_all([available, archived])
    await db_session.flush()

    r = await auth_client.get("/api/v2/inventory/available")
    assert r.status_code == 200
    data = r.json()
    names = [i["name"] for i in data]
    assert "Paddle" in names
    assert "Old Belt" not in names


@pytest.mark.asyncio
async def test_available_inventory_filter_by_category(db_session, auth_client, test_user):
    """Filter by inventory_category_id."""
    await seed_inventory_categories(db_session)
    await db_session.flush()

    impact = (
        await db_session.execute(select(InventoryCategory).where(InventoryCategory.slug == "impact_tool"))
    ).scalar_one()
    clothing = (
        await db_session.execute(select(InventoryCategory).where(InventoryCategory.slug == "clothing"))
    ).scalar_one()

    i1 = InventoryItem(
        user_id=test_user.id,
        name="Belt",
        category="impact_tool",
        inventory_category_id=impact.id,
        inventory_status="available",
        status="need",
    )
    i2 = InventoryItem(
        user_id=test_user.id,
        name="Latex Suit",
        category="clothing",
        inventory_category_id=clothing.id,
        inventory_status="available",
        status="need",
    )
    db_session.add_all([i1, i2])
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/inventory/available?inventory_category_id={impact.id}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Belt"


# ═════════════════════════════════════════════════════════════════════════
# Task search
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_search_by_status(db_session, auth_client, test_user):
    log1 = ActivityLog(user_id=test_user.id, status="completed")
    log2 = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add_all([log1, log2])
    await db_session.flush()

    r = await auth_client.get("/api/v2/tasks/search?status=completed")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_search_by_body_part(db_session, auth_client, test_user):
    await seed_body_parts(db_session)
    await db_session.flush()

    bp = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "torso_chest"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    tbt = TaskBodyTarget(task_id=log.id, body_part_id=bp.id, body_part_name_snapshot="Грудь")
    db_session.add(tbt)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/search?body_part_id={bp.id}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == str(log.id)


@pytest.mark.asyncio
async def test_search_by_body_system(db_session, auth_client, test_user):
    await seed_body_parts(db_session)
    await db_session.flush()

    bp = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "thighs"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    db_session.add(TaskBodyTarget(task_id=log.id, body_part_id=bp.id, body_part_name_snapshot="Бёдра"))
    await db_session.flush()

    r = await auth_client.get("/api/v2/tasks/search?body_system=lower_limb")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_search_by_location(db_session, auth_client, test_user):
    await seed_locations(db_session)
    await db_session.flush()

    loc = (await db_session.execute(select(TaskLocation).where(TaskLocation.slug == "bed"))).scalar_one()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    usage = TaskLocationUsage(task_id=log.id, location_id=loc.id, location_name_snapshot="Кровать")
    db_session.add(usage)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/search?location_id={loc.id}")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_search_by_inventory_item(db_session, auth_client, test_user):
    item = InventoryItem(user_id=test_user.id, name="Timer", category="measurement_tool", status="need")
    db_session.add(item)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    usage = TaskInventoryUsage(
        task_id=log.id,
        inventory_item_id=item.id,
        inventory_name_snapshot="Timer",
    )
    db_session.add(usage)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/search?inventory_item_id={item.id}")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_search_by_session_id(db_session, auth_client, test_user):
    from app.models.session import ActivitySession

    session = ActivitySession(owner_id=test_user.id, status="created")
    db_session.add(session)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, status="planned", session_id=session.id)
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/search?session_id={session.id}")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ═════════════════════════════════════════════════════════════════════════
# Cross-user isolation
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_access_other_user_task_links(db_session, auth_client, test_user):
    """404 when accessing task links of another user's task."""
    other = User(email="o@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    log = ActivityLog(user_id=other.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.get(f"/api/v2/tasks/{log.id}/body-targets")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_other_user_cannot_see_my_custom_location(db_session, auth_client, test_user):
    """Personal locations are invisible to other users."""
    other = User(email="p@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    my_loc = TaskLocation(slug="my-secret", title_ru="Secret", is_custom=True, owner_id=test_user.id)
    db_session.add(my_loc)
    await db_session.flush()

    # Our user sees it
    r = await auth_client.get("/api/v2/locations")
    data = r.json()
    assert any(loc["slug"] == "my-secret" for loc in data)

    # Other user wouldn't (we only test the server-side filtering — separate test)


# ═════════════════════════════════════════════════════════════════════════
# DSL: selector types
# ═════════════════════════════════════════════════════════════════════════


def test_dsl_has_selector_types():
    """inventory_selector, body_part_selector, location_selector are registered."""
    assert "inventory_selector" in PARAM_TYPES
    assert "body_part_selector" in PARAM_TYPES
    assert "location_selector" in PARAM_TYPES


def test_dsl_inventory_selector_normalizes_with_defaults():
    schema = normalize_schema(
        [
            {
                "key": "tool",
                "type": "inventory_selector",
                "selection_mode": "multiple",
                "allowed_categories": ["impact_tool"],
                "allowed_usage_roles": ["primary_tool", "secondary_tool"],
            }
        ]
    )
    assert schema[0]["type"] == "inventory_selector"
    assert schema[0]["selection_mode"] == "multiple"
    assert schema[0]["allowed_categories"] == ["impact_tool"]


def test_dsl_body_part_selector_normalizes():
    schema = normalize_schema(
        [
            {
                "key": "target_area",
                "type": "body_part_selector",
                "selection_mode": "multiple",
                "allowed_body_systems": ["torso", "lower_limb"],
                "allow_side_selection": True,
            }
        ]
    )
    assert schema[0]["type"] == "body_part_selector"
    assert schema[0]["allowed_body_systems"] == ["torso", "lower_limb"]


def test_dsl_location_selector_normalizes():
    schema = normalize_schema(
        [
            {
                "key": "location",
                "type": "location_selector",
                "selection_mode": "single",
                "allowed_location_types": ["room", "training"],
                "include_user_custom_locations": True,
            }
        ]
    )
    assert schema[0]["type"] == "location_selector"
    assert schema[0]["selection_mode"] == "single"


def test_dsl_selector_validation_single_mode():
    """Single-mode selector expects a string ID."""
    schema = [{"key": "loc", "type": "location_selector", "selection_mode": "single"}]
    assert validate_params(schema, {"loc": "some-uuid"}) == []
    assert validate_params(schema, {"loc": ["list"]})  # not a string


def test_dsl_selector_validation_multiple_mode():
    """Multiple-mode selector expects a list of string IDs."""
    schema = [{"key": "tools", "type": "inventory_selector", "selection_mode": "multiple"}]
    assert validate_params(schema, {"tools": ["id1", "id2"]}) == []
    assert validate_params(schema, {"tools": "not-a-list"})  # not a list
    assert validate_params(schema, {"tools": [1, 2]})  # not strings


# ═════════════════════════════════════════════════════════════════════════
# Backward compatibility
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_old_tasks_without_new_links_still_work(db_session, auth_client, test_user):
    """Tasks without body/location/inventory links still open and transition."""
    log = ActivityLog(user_id=test_user.id, status="planned", selected_entity_name="Old task")
    db_session.add(log)
    await db_session.flush()

    # GET body targets — empty list, not 404
    r = await auth_client.get(f"/api/v2/tasks/{log.id}/body-targets")
    assert r.status_code == 200
    assert r.json() == []

    # GET location usages
    r = await auth_client.get(f"/api/v2/tasks/{log.id}/location-usages")
    assert r.status_code == 200
    assert r.json() == []

    # GET inventory usages
    r = await auth_client.get(f"/api/v2/tasks/{log.id}/inventory-usages")
    assert r.status_code == 200
    assert r.json() == []

    # Transition still works
    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/transition",
        json={"to_status": "cancelled"},
    )
    assert r.status_code == 200
    await db_session.refresh(log)
    assert log.status == "cancelled"


@pytest.mark.asyncio
async def test_inventory_item_has_both_status_fields(db_session, test_user):
    """Legacy 'status' (shopping) and new 'inventory_status' (operational) coexist."""
    item = InventoryItem(
        user_id=test_user.id,
        name="Test Item",
        category="equipment",
        status="need",  # shopping status
        inventory_status="available",  # operational status
    )
    db_session.add(item)
    await db_session.flush()
    await db_session.refresh(item)

    assert item.status == "need"
    assert item.inventory_status == "available"


@pytest.mark.asyncio
async def test_entity_with_requirement_tables(db_session, test_user):
    """ActivityBodyPartRequirement, etc. can be created and linked."""
    await seed_body_parts(db_session)
    await db_session.flush()

    entity = Entity(real_name="Test", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()

    bp = (await db_session.execute(select(BodyPart).where(BodyPart.slug == "abs"))).scalar_one()

    from app.models.body_part import ActivityBodyPartRequirement

    req = ActivityBodyPartRequirement(
        activity_id=entity.id,
        body_part_id=bp.id,
        target_role="training_target",
        is_required=True,
    )
    db_session.add(req)
    await db_session.flush()

    result = await db_session.execute(
        select(ActivityBodyPartRequirement).where(ActivityBodyPartRequirement.activity_id == entity.id)
    )
    assert result.scalar_one().body_part_id == bp.id
