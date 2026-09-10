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


@pytest.mark.asyncio
async def test_update_stock_endpoints(auth_client, test_user, db_session):
    med = Medication(user_id=test_user.id, name="Магний B6", kind="supplement", unit="таб")
    kit1 = MedKit(user_id=test_user.id, name="Домашняя")
    kit2 = MedKit(user_id=test_user.id, name="Офис")
    db_session.add_all([med, kit1, kit2])
    await db_session.commit()

    stock = MedStock(
        user_id=test_user.id,
        medication_id=med.id,
        kit_id=kit1.id,
        quantity=30.0,
        unit="таб",
        lot_number="L1",
        notes="Первичный запас",
    )
    db_session.add(stock)
    await db_session.commit()

    # 1. Update stock form endpoint
    resp = await auth_client.post(
        f"/med-stocks/{stock.id}/update",
        data={
            "quantity": "45.5",
            "unit": "капс",
            "expiry_date": "2028-01-01",
            "lot_number": "L2-MOD",
            "kit_id": str(kit2.id),
            "notes": "Перенесено в офис",
        },
    )
    assert resp.status_code == 303
    await db_session.refresh(stock)
    assert stock.quantity == 45.5
    assert stock.unit == "капс"
    assert stock.lot_number == "L2-MOD"
    assert stock.kit_id == kit2.id
    assert stock.expiry_date.isoformat() == "2028-01-01"
    assert stock.notes == "Перенесено в офис"

    # 2. Get kit via JSON API
    api_resp = await auth_client.get(f"/api/v2/medications/kits/{kit2.id}")
    assert api_resp.status_code == 200
    k_data = api_resp.json()
    assert k_data["name"] == "Офис"
    assert len(k_data["items"]) == 1
    assert k_data["items"][0]["id"] == str(stock.id)
    assert k_data["items"][0]["quantity"] == 45.5

    # 3. Update stock via JSON API
    put_resp = await auth_client.put(
        f"/api/v2/medications/stocks/{stock.id}",
        json={"quantity": 50.0, "unit": "таб", "notes": "API update"},
    )
    assert put_resp.status_code == 200
    await db_session.refresh(stock)
    assert stock.quantity == 50.0
    assert stock.unit == "таб"


@pytest.mark.asyncio
async def test_update_course_item_schedule(auth_client, test_user, db_session):
    med = Medication(user_id=test_user.id, name="Верошпирон", kind="medication", unit="таб")
    course = MedCourse(user_id=test_user.id, name="Терапия отеков")
    db_session.add_all([med, course])
    await db_session.commit()

    # Add item to course
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

    # Update item schedule
    upd_resp = await auth_client.post(
        f"/med-courses/{course.id}/items/{sched.id}/update",
        data={
            "dose_quantity": "2",
            "dose_unit": "таб",
            "times_per_day": "2",
            "times_of_day": "09:00, 18:00",
            "frequency_type": "daily",
            "food_relation": "after_meal",
            "duration_days": "14",
        },
    )
    assert upd_resp.status_code == 303
    await db_session.refresh(sched)
    assert sched.dose_quantity == 2.0
    assert sched.dose_unit == "таб"
    assert sched.times_per_day == 2
    assert sched.times_of_day == ["09:00", "18:00"]
    assert sched.food_relation == "after_meal"


@pytest.mark.asyncio
async def test_batch_combine_course_slots(auth_client, test_user, db_session):
    med1 = Medication(user_id=test_user.id, name="Фемостон", kind="medication", unit="таб")
    med2 = Medication(user_id=test_user.id, name="Праджисан", kind="medication", unit="капс")
    course = MedCourse(user_id=test_user.id, name="ЗГТ протокол")
    db_session.add_all([med1, med2, course])
    await db_session.commit()

    # Add both medications
    await auth_client.post(
        f"/med-courses/{course.id}/items",
        data={"medication_id": str(med1.id), "dose_quantity": "1", "frequency_type": "daily"},
    )
    await auth_client.post(
        f"/med-courses/{course.id}/items",
        data={"medication_id": str(med2.id), "dose_quantity": "1", "frequency_type": "daily"},
    )

    scheds = (await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id))).scalars().all()
    assert len(scheds) == 2

    # Combine slots via endpoint
    resp = await auth_client.post(
        f"/med-courses/{course.id}/combine-slots",
        data={
            "schedule_ids": [str(s.id) for s in scheds],
            "times_of_day": "08:30, 20:30",
            "food_relation": "after_meal",
        },
    )
    assert resp.status_code == 303

    for s in scheds:
        await db_session.refresh(s)
        assert s.times_of_day == ["08:30", "20:30"]
        assert s.food_relation == "after_meal"

    # Verify course_summary grouped_slots
    from app.services.med.course import course_summary

    summary = await course_summary(db_session, course)
    assert "grouped_slots" in summary
    assert len(summary["grouped_slots"]) == 2  # 08:30 and 20:30
    slot_times = [gs["slot"] for gs in summary["grouped_slots"]]
    assert "08:30" in slot_times
    assert "20:30" in slot_times
    slot_830 = next(gs for gs in summary["grouped_slots"] if gs["slot"] == "08:30")
    assert len(slot_830["items"]) == 2
    assert slot_830["items"][0]["food_relation"] == "after_meal"


@pytest.mark.asyncio
async def test_add_medication_to_kit_without_stock(auth_client, test_user, db_session):
    med = Medication(user_id=test_user.id, name="Лоперамид", kind="medication", unit="капс")
    kit = MedKit(user_id=test_user.id, name="Походная")
    db_session.add_all([med, kit])
    await db_session.commit()

    # 1. Add item to kit composition with 0 stock
    resp = await auth_client.post(
        f"/med-kits/{kit.id}/add-item",
        data={"medication_id": str(med.id), "notes": "Взять в поход"},
    )
    assert resp.status_code == 303

    stmt = select(MedStock).where(MedStock.kit_id == kit.id, MedStock.medication_id == med.id)
    stocks = (await db_session.execute(stmt)).scalars().all()
    assert len(stocks) == 1
    st = stocks[0]
    assert st.quantity == 0.0
    assert st.unit == "капс"
    assert st.expiry_date is None
    assert st.lot_number is None
    assert st.notes == "Взять в поход"

    # 2. Re-adding the same medication with 0 stock doesn't duplicate
    resp2 = await auth_client.post(
        f"/med-kits/{kit.id}/add-stock",
        data={"medication_id": str(med.id), "quantity": "0", "notes": "Обновленная заметка"},
    )
    assert resp2.status_code == 303
    stocks2 = (await db_session.execute(stmt)).scalars().all()
    assert len(stocks2) == 1
    assert stocks2[0].notes == "Обновленная заметка"


@pytest.mark.asyncio
async def test_replenish_unstocked_kit_placeholder(auth_client, test_user, db_session):
    med = Medication(user_id=test_user.id, name="Парацетамол 500 мг", kind="medication", unit="таб")
    kit = MedKit(user_id=test_user.id, name="Офисная")
    db_session.add_all([med, kit])
    await db_session.commit()

    # 1. Add without stock (composition only)
    await auth_client.post(
        f"/med-kits/{kit.id}/add-stock",
        data={"medication_id": str(med.id), "quantity": "0"},
    )
    stmt = select(MedStock).where(MedStock.kit_id == kit.id, MedStock.medication_id == med.id)
    placeholder = (await db_session.execute(stmt)).scalar_one()
    assert placeholder.quantity == 0.0

    # 2. Later replenish with actual quantity, expiry and lot
    resp = await auth_client.post(
        f"/med-kits/{kit.id}/add-stock",
        data={
            "medication_id": str(med.id),
            "quantity": "20",
            "unit": "таб",
            "expiry_date": "2028-06-01",
            "lot_number": "BATCH-2028",
            "notes": "Куплено для офиса",
        },
    )
    assert resp.status_code == 303

    stocks = (await db_session.execute(stmt)).scalars().all()
    assert len(stocks) == 1  # Placeholder updated in-place!
    upd = stocks[0]
    assert upd.id == placeholder.id
    assert upd.quantity == 20.0
    assert upd.expiry_date.isoformat() == "2028-06-01"
    assert upd.lot_number == "BATCH-2028"
    assert upd.notes == "Куплено для офиса"

