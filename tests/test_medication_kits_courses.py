import pytest
from sqlalchemy import select

from app.models.medication import MedCourse, Medication, MedKit, MedSchedule, MedStock


@pytest.mark.asyncio
async def test_update_kit_endpoint(auth_client, test_user, db_session):
    # 1. Create kit
    resp = await auth_client.post(
        "/med-kits",
        data={"name": "Аптечка авто", "location": "Багажник", "notes": "В машине"},
    )
    assert resp.status_code == 303
    stmt = select(MedKit).where(MedKit.user_id == test_user.id, MedKit.name == "Аптечка авто")
    kit = (await db_session.execute(stmt)).scalar_one()

    # 2. Update kit
    resp_upd = await auth_client.post(
        f"/med-kits/{kit.id}/update",
        data={"name": "Аптечка в авто (обновлена)", "location": "Под сиденьем", "notes": "Проверена"},
    )
    assert resp_upd.status_code == 303
    await db_session.refresh(kit)
    assert kit.name == "Аптечка в авто (обновлена)"
    assert kit.location == "Под сиденьем"
    assert kit.notes == "Проверена"


@pytest.mark.asyncio
async def test_add_stock_to_kit_endpoint(auth_client, test_user, db_session):
    # 1. Create med and kit
    med = Medication(user_id=test_user.id, name="Анальгин", kind="medication", unit="таб")
    kit = MedKit(user_id=test_user.id, name="Домашняя")
    db_session.add_all([med, kit])
    await db_session.commit()

    # 2. Add stock directly into kit
    resp = await auth_client.post(
        f"/med-kits/{kit.id}/add-stock",
        data={
            "medication_id": str(med.id),
            "quantity": "20",
            "unit": "таб",
            "expiry_date": "2027-05-01",
            "lot_number": "BATCH-777",
            "notes": "Куплено в аптеке",
        },
    )
    assert resp.status_code == 303

    stock = (await db_session.execute(select(MedStock).where(MedStock.kit_id == kit.id))).scalar_one()
    assert stock.medication_id == med.id
    assert stock.quantity == 20.0
    assert stock.lot_number == "BATCH-777"
    assert stock.expiry_date.isoformat() == "2027-05-01"


@pytest.mark.asyncio
async def test_update_course_endpoint(auth_client, test_user, db_session):
    # 1. Create course
    resp = await auth_client.post(
        "/med-courses",
        data={"name": "Курс витаминов", "start_date": "2026-09-01", "notes": "Осень"},
    )
    assert resp.status_code == 303
    stmt = select(MedCourse).where(MedCourse.user_id == test_user.id, MedCourse.name == "Курс витаминов")
    course = (await db_session.execute(stmt)).scalar_one()

    # 2. Update course
    resp_upd = await auth_client.post(
        f"/med-courses/{course.id}/update",
        data={
            "name": "Курс витаминов B+C",
            "start_date": "2026-09-01",
            "end_date": "2026-10-01",
            "status": "active",
            "notes": "Осенний укрепляющий",
        },
    )
    assert resp_upd.status_code == 303
    await db_session.refresh(course)
    assert course.name == "Курс витаминов B+C"
    assert course.end_date.isoformat() == "2026-10-01"
    assert course.status == "active"


@pytest.mark.asyncio
async def test_delete_course_item_endpoint(auth_client, test_user, db_session):
    med = Medication(user_id=test_user.id, name="Омега-3", kind="supplement")
    course = MedCourse(user_id=test_user.id, name="Суставы")
    db_session.add_all([med, course])
    await db_session.commit()

    resp = await auth_client.post(
        f"/med-courses/{course.id}/items",
        data={
            "medication_id": str(med.id),
            "dose_quantity": "1",
            "frequency_type": "daily",
        },
    )
    assert resp.status_code == 303
    sched = (await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id))).scalar_one()

    # Delete course item
    del_resp = await auth_client.post(f"/med-courses/{course.id}/items/{sched.id}/delete")
    assert del_resp.status_code == 303
    left = (await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id))).scalars().all()
    assert len(left) == 0


@pytest.mark.asyncio
async def test_scan_barcode_endpoint(auth_client, test_user, db_session):
    # Create medication with GTIN in notes
    med = Medication(user_id=test_user.id, name="Кеторол Экспресс", kind="medication", notes="GTIN: 04601234567890")
    db_session.add(med)
    await db_session.commit()

    # 1. Post raw DataMatrix code
    raw_code = "(01)04601234567890(21)SER12345(17)270831(10)LOT9988"
    resp = await auth_client.post(
        "/medications/scan-barcode",
        data={"raw_code": raw_code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["parsed"]["gtin"] == "04601234567890"
    assert data["parsed"]["lot_number"] == "LOT9988"
    assert data["parsed"]["expiry_date"] == "2027-08-31"
    assert data["matched_medication"] is not None
    assert data["matched_medication"]["name"] == "Кеторол Экспресс"
