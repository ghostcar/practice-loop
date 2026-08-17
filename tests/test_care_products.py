"""Care Products tests (Шаг 16b, ADR-092).

Каталог средств/косметики для ухода с привязкой к инвентарю (inventory_item_id,
FK SET NULL) и связью «средства использованы в записи» (care_entry_products,
many-to-many). Relief-only (PD-013): уход без игровой интеграции.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.care import CareEntry, CareEntryProduct, CareProduct
from app.models.life import InventoryItem
from app.models.user import User

TODAY = date.today()


async def _add_inventory(db_session, user_id: User, name: str = "Cleansing gel") -> InventoryItem:
    item = InventoryItem(user_id=user_id.id, category="cosmetics", name=name, quantity=1, quantity_needed=1)
    db_session.add(item)
    await db_session.flush()
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Page + products catalog
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_care_page_products_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "care_no_products" in resp.text or "No products yet" in resp.text


@pytest.mark.asyncio
async def test_add_product_with_inventory_link(auth_client, test_user, db_session):
    inv = await _add_inventory(db_session, test_user, name="Gentle cleanser")
    resp = await auth_client.post(
        "/care/products",
        data={
            "name": "Cleansing gel",
            "category": "cleanser",
            "brand": "CeraVe",
            "notes": "evening",
            "inventory_item_id": str(inv.id),
        },
    )
    assert resp.status_code == 303, resp.text
    product = (await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))).scalar_one()
    assert product.name == "Cleansing gel"
    assert product.category == "cleanser"
    assert product.brand == "CeraVe"
    assert product.inventory_item_id == inv.id

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Cleansing gel" in resp.text
    assert "Gentle cleanser" in resp.text  # inventory badge


@pytest.mark.asyncio
async def test_add_product_invalid_category_defaults(auth_client, test_user, db_session):
    resp = await auth_client.post("/care/products", data={"name": "X", "category": "bogus"})
    assert resp.status_code == 303, resp.text
    p = (await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))).scalar_one()
    assert p.category == "other"


@pytest.mark.asyncio
async def test_add_product_foreign_inventory_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_inv = await _add_inventory(db_session, other, name="Other's item")

    resp = await auth_client.post(
        "/care/products", data={"name": "P", "inventory_item_id": str(other_inv.id)}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_product_cascades_join_rows(auth_client, test_user, db_session):
    inv = await _add_inventory(db_session, test_user)
    await auth_client.post(
        "/care/products", data={"name": "Serum", "category": "serum", "inventory_item_id": str(inv.id)}
    )
    product = (await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))).scalar_one()

    # bind product to an entry
    await auth_client.post(
        "/care/entries", data={"entry_date": TODAY.isoformat(), "product_ids": str(product.id)}
    )
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    joins = (
        await db_session.execute(select(CareEntryProduct).where(CareEntryProduct.entry_id == entry.id))
    ).scalars().all()
    assert len(joins) == 1

    resp = await auth_client.post(f"/care/products/{product.id}/delete")
    assert resp.status_code == 303
    remaining_joins = (
        await db_session.execute(select(CareEntryProduct).where(CareEntryProduct.entry_id == entry.id))
    ).scalars().all()
    assert len(remaining_joins) == 0  # CASCADE


# ─────────────────────────────────────────────────────────────────────────────
# Entry ↔ products (many-to-many)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_with_products_form(auth_client, test_user, db_session):
    await auth_client.post("/care/products", data={"name": "Toner", "category": "toner"})
    await auth_client.post("/care/products", data={"name": "Moisturizer", "category": "moisturizer"})
    products = (
        await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))
    ).scalars().all()
    assert len(products) == 2

    resp = await auth_client.post(
        "/care/entries",
        data={
            "entry_date": TODAY.isoformat(),
            "product_ids": [str(products[0].id), str(products[1].id)],
        },
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(CareEntry).where(CareEntry.user_id == test_user.id))).scalar_one()
    joins = (
        await db_session.execute(select(CareEntryProduct).where(CareEntryProduct.entry_id == entry.id))
    ).scalars().all()
    assert {j.product_id for j in joins} == {p.id for p in products}

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Toner" in resp.text
    assert "Moisturizer" in resp.text


@pytest.mark.asyncio
async def test_entry_foreign_product_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_product = CareProduct(user_id=other.id, name="X")
    db_session.add(other_product)
    await db_session.flush()

    resp = await auth_client.post(
        "/care/entries", data={"entry_date": TODAY.isoformat(), "product_ids": str(other_product.id)}
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_add_product_and_summary(auth_client, test_user, db_session):
    inv = await _add_inventory(db_session, test_user, name="Sunscreen")
    resp = await auth_client.post(
        "/api/v2/care/products",
        json={"name": "SPF50", "category": "sun", "brand": "LPR", "inventory_item_id": str(inv.id)},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["category"] == "sun"
    assert data["inventory_item_id"] == str(inv.id)

    resp = await auth_client.get("/api/v2/care")
    assert resp.status_code == 200
    products = resp.json()["products"]
    assert len(products) == 1
    assert products[0]["name"] == "SPF50"


@pytest.mark.asyncio
async def test_json_entry_with_products(auth_client, test_user, db_session):
    await auth_client.post("/api/v2/care/products", json={"name": "Cleanser", "category": "cleanser"})
    product = (await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))).scalar_one()

    resp = await auth_client.post(
        "/api/v2/care/entries",
        json={"entry_date": TODAY.isoformat(), "product_ids": [str(product.id)]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["product_ids"] == [str(product.id)]


@pytest.mark.asyncio
async def test_json_delete_product(auth_client, test_user, db_session):
    await auth_client.post("/api/v2/care/products", json={"name": "Mask", "category": "mask"})
    product = (await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))).scalar_one()
    resp = await auth_client.delete(f"/api/v2/care/products/{product.id}")
    assert resp.status_code == 204
    remaining = (
        await db_session.execute(select(CareProduct).where(CareProduct.user_id == test_user.id))
    ).scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_json_foreign_inventory_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_inv = await _add_inventory(db_session, other, name="Other's")
    resp = await auth_client.post(
        "/api/v2/care/products", json={"name": "P", "inventory_item_id": str(other_inv.id)}
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    await auth_client.post("/care/products", data={"name": "Private serum", "notes": "private"})
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
    assert not any("private" in (p.get("notes") or "") for p in resp.json()["products"])


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_care_products_no_gamification():
    """PD-013: средства ухода не применяют игровую механику (по импортам и вызовам)."""
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
