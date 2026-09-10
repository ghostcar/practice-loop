from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.medication import Medication, MedIntake, MedKit, MedSchedule, MedStock
from app.services import med_service as svc
from app.services.med.regimen import group_meds_by_meal
from app.services.med.wizard import check_drug_interactions


@pytest.mark.asyncio
async def test_prn_intake_and_fefo_deduction(db_session, test_user):
    """Тест ситуативного приёма (PRN) со списанием по FEFO из выбранной аптечки."""
    # 1. Создаем препарат и 2 аптечки
    med = Medication(user_id=test_user.id, name="Нурофен Экспресс", kind="medication", unit="капс")
    kit_home = MedKit(user_id=test_user.id, name="Домашняя аптечка", location="Спальня")
    kit_office = MedKit(user_id=test_user.id, name="Офисная аптечка", location="Офис")
    db_session.add_all([med, kit_home, kit_office])
    await db_session.flush()

    today = date.today()
    # Две партии в офисной аптечке: одна годна до today+10, другая до today+100
    st_near = MedStock(
        user_id=test_user.id,
        medication_id=med.id,
        kit_id=kit_office.id,
        quantity=5.0,
        expiry_date=today + timedelta(days=10),
    )
    st_far = MedStock(
        user_id=test_user.id,
        medication_id=med.id,
        kit_id=kit_office.id,
        quantity=10.0,
        expiry_date=today + timedelta(days=100),
    )
    # Партия дома
    st_home = MedStock(
        user_id=test_user.id,
        medication_id=med.id,
        kit_id=kit_home.id,
        quantity=20.0,
        expiry_date=today + timedelta(days=5),
    )
    db_session.add_all([st_near, st_far, st_home])
    await db_session.commit()

    # 2. Ситуативный приём из офисной аптечки (приоритет партии с ближайшим сроком в офисе)
    intake = await svc.record_prn_intake(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        quantity_taken=2.0,
        kit_id=kit_office.id,
        symptom_reason="Острая головная боль",
        notes="Принято перед митингом",
    )
    await db_session.commit()

    assert intake.is_prn is True
    assert intake.kit_id == kit_office.id
    assert intake.stock_id == st_near.id
    assert "Острая головная боль" in (intake.notes or "")

    await db_session.refresh(st_near)
    await db_session.refresh(st_far)
    await db_session.refresh(st_home)

    # 5.0 - 2.0 = 3.0 в ближайшей партии
    assert st_near.quantity == 3.0
    assert st_far.quantity == 10.0
    assert st_home.quantity == 20.0


@pytest.mark.asyncio
async def test_delete_intake_restores_stock(db_session, test_user):
    """Тест отмены приёма: списанное количество возвращается в партию MedStock."""
    med = Medication(user_id=test_user.id, name="Но-шпа", kind="medication")
    kit = MedKit(user_id=test_user.id, name="Сумка")
    db_session.add_all([med, kit])
    await db_session.flush()

    stock = MedStock(user_id=test_user.id, medication_id=med.id, kit_id=kit.id, quantity=10.0)
    db_session.add(stock)
    await db_session.commit()

    intake = await svc.record_prn_intake(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        quantity_taken=2.0,
        kit_id=kit.id,
    )
    await db_session.commit()
    await db_session.refresh(stock)
    assert stock.quantity == 8.0

    # Отменяем факт приёма
    await svc.delete_intake(db_session, user_id=test_user.id, intake_id=intake.id)
    await db_session.commit()
    await db_session.refresh(stock)
    # Количество восстановилось
    assert stock.quantity == 10.0

    # Запись удалена
    deleted = (await db_session.execute(select(MedIntake).where(MedIntake.id == intake.id))).scalar_one_or_none()
    assert deleted is None


@pytest.mark.asyncio
async def test_meal_grouping():
    """Тест иерархической группировки слотов по типу приёма пищи."""
    items = [
        {"medication_name": "Эстрадиол", "food_relation": "independent", "taken": False},
        {"medication_name": "Омега-3", "food_relation": "during_meal", "taken": True},
        {"medication_name": "Коллаген", "food_relation": "empty_stomach", "taken": False},
        {"medication_name": "Магний", "food_relation": "after_meal", "taken": False},
        {"medication_name": "Домперидон", "food_relation": "before_meal", "taken": True},
    ]

    groups = group_meds_by_meal(items)
    # Порядок групп: empty_stomach, before_meal, during_meal, after_meal, independent
    labels = [g["food_relation"] for g in groups]
    assert labels == ["empty_stomach", "before_meal", "during_meal", "after_meal", "independent"]

    # Проверка свойств
    empty_grp = next(g for g in groups if g["food_relation"] == "empty_stomach")
    assert empty_grp["label"] == "Натощак"
    assert len(empty_grp["meds"]) == 1
    assert empty_grp["pending"] is True


@pytest.mark.asyncio
async def test_drug_interactions_screening():
    """Тест экспресс-проверки нежелательных фармакологических комбинаций."""
    warnings_safe = check_drug_interactions(["Витамин D3", "Омега-3", "Магний"])
    # Безопасная комбинация
    assert len(warnings_safe) == 0

    # Опасная комбинация: Верошпирон + Аспаркам (гиперкалиемия)
    warnings_danger = check_drug_interactions(["Верошпирон 25 мг", "Аспаркам таб"])
    assert len(warnings_danger) >= 1
    assert any(w["level"] == "danger" for w in warnings_danger)

    # Нежелательная комбинация: Железо + Кальций
    warnings_iron = check_drug_interactions(["Мальтофер 100 мг", "Кальций D3 Никомед"])
    assert len(warnings_iron) >= 1
    assert any("всасывание" in w["title"].lower() or "всасывание" in w["description"].lower() for w in warnings_iron)


@pytest.mark.asyncio
async def test_course_wizard_preset_and_apply(db_session, test_user):
    """Тест генерации протокола курса и применения в 1 клик."""
    kit = MedKit(user_id=test_user.id, name="Аптечка курса", location="Комод")
    db_session.add(kit)
    await db_session.commit()

    # 1. Генерация по пресету
    proto = await svc.generate_course_protocol(db_session, user_id=test_user.id, goal="hrt_lactation")
    assert "ЗГТ" in proto["course_name"]
    assert len(proto["phases"]) >= 2

    # 2. Применение курса
    course = await svc.apply_generated_course(
        db_session,
        user_id=test_user.id,
        course_data=proto,
        kit_id=kit.id,
    )
    assert course.id is not None
    assert course.user_id == test_user.id

    # 3. Проверка созданных расписаний
    schedules = (
        (await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id)))
        .scalars()
        .all()
    )
    assert len(schedules) >= 4
    for s in schedules:
        assert s.preferred_kit_id == kit.id
        assert s.dose_quantity > 0
        assert s.frequency_type == "daily"


@pytest.mark.asyncio
async def test_fefo_no_blind_deduction_when_kit_exhausted_or_missing(db_session, test_user):
    """Тест исключения слепого автосписания (ADR-207):
    - Если в указанной аптечке запас исчерпан, система НЕ списывает из чужой аптечки.
    - Если аптечка не указана, списание не производится без явного выбора пользователя.
    - При явном выборе аптечки списание идет строго из неё.
    """
    med = Medication(user_id=test_user.id, name="Эстрадиол 2 мг", kind="medication")
    kit_target = MedKit(user_id=test_user.id, name="Целевая аптечка")
    kit_other = MedKit(user_id=test_user.id, name="Другая аптечка")
    db_session.add_all([med, kit_target, kit_other])
    await db_session.flush()

    # В целевой аптечке 0, в другой аптечке 10 шт
    stock_other = MedStock(user_id=test_user.id, medication_id=med.id, kit_id=kit_other.id, quantity=10.0)
    db_session.add(stock_other)
    await db_session.commit()

    sched_with_target = MedSchedule(
        user_id=test_user.id,
        medication_id=med.id,
        preferred_kit_id=kit_target.id,
        dose_quantity=1.0,
        frequency_type="daily",
    )
    sched_no_kit = MedSchedule(
        user_id=test_user.id,
        medication_id=med.id,
        preferred_kit_id=None,
        dose_quantity=1.0,
        frequency_type="daily",
    )
    db_session.add_all([sched_with_target, sched_no_kit])
    await db_session.commit()

    # Случай 1: Назначена kit_target, но в ней 0 шт. В kit_other 10 шт.
    # Приём не должен трогать kit_other!
    intake1 = await svc.record_intake(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        schedule_id=sched_with_target.id,
        status="taken",
        quantity_taken=1.0,
    )
    await db_session.commit()
    await db_session.refresh(stock_other)

    assert intake1.stock_id is None
    assert stock_other.quantity == 10.0  # Чужая аптечка НЕ тронута!
    assert "Запас в указанной аптечке исчерпан" in (intake1.notes or "")

    # Случай 2: Аптечка не назначена в расписании (preferred_kit_id is None).
    # Без явного указания kit_id списание не производится!
    intake2 = await svc.record_intake(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        schedule_id=sched_no_kit.id,
        status="taken",
        quantity_taken=1.0,
    )
    await db_session.commit()
    await db_session.refresh(stock_other)

    assert intake2.stock_id is None
    assert stock_other.quantity == 10.0  # Снова не списано вслепую
    assert "Аптечка не указана" in (intake2.notes or "")

    # Случай 3: Пользователь явно выбрал kit_other в UI / боте
    intake3 = await svc.record_intake(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        schedule_id=sched_with_target.id,
        kit_id=kit_other.id,
        status="taken",
        quantity_taken=1.0,
    )
    await db_session.commit()
    await db_session.refresh(stock_other)

    assert intake3.stock_id == stock_other.id
    assert stock_other.quantity == 9.0  # Списано строго по явному выбору


@pytest.mark.asyncio
async def test_delete_course_cascades_and_removes_schedules_and_today_tasks(db_session, test_user):
    """Тест каскадного удаления расписаний и задач дня при удалении курса."""
    # 1. Применяем сгенерированный курс
    raw_proto = await svc.generate_course_protocol(db_session, user_id=test_user.id, goal="hrt_lactation")
    course = await svc.apply_generated_course(db_session, test_user.id, raw_proto, kit_id=None)
    await db_session.commit()

    # 2. Проверяем, что расписания созданы и видны в сводке на сегодня
    schedules_before = (
        await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id))
    ).scalars().all()
    assert len(schedules_before) >= 4

    summary_before = await svc.schedule_summary(db_session, test_user.id)
    due_ids_before = {d["id"] for d in summary_before["due"]}
    for s in schedules_before:
        assert str(s.id) in due_ids_before

    # 3. Удаляем курс
    await svc.delete_course(db_session, test_user.id, course.id)
    await db_session.commit()

    # 4. Проверяем, что связанные расписания полностью удалены
    schedules_after = (
        await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == course.id))
    ).scalars().all()
    assert len(schedules_after) == 0

    # Проверяем, что их нет и как осиротевших расписаний (course_id IS NULL)
    deleted_sched_ids = [s.id for s in schedules_before]
    orphans = (
        await db_session.execute(select(MedSchedule).where(MedSchedule.id.in_(deleted_sched_ids)))
    ).scalars().all()
    assert len(orphans) == 0

    # 5. Проверяем, что в расписании на сегодня задачи приема полностью исчезли
    summary_after = await svc.schedule_summary(db_session, test_user.id)
    due_ids_after = {d["id"] for d in summary_after["due"]}
    for sid in deleted_sched_ids:
        assert str(sid) not in due_ids_after

    # 6. Проверяем, что автоматически созданные неиспользуемые лекарства удалены из справочника
    for s in schedules_before:
        m = (
            await db_session.execute(select(Medication).where(Medication.id == s.medication_id))
        ).scalar_one_or_none()
        # Препарат без остатков и других назначений должен быть удален
        assert m is None


@pytest.mark.asyncio
async def test_pause_course_deactivates_schedules_and_hides_from_today(db_session, test_user):
    """Тест приостановки курса: расписания деактивируются и не попадают в план дня."""
    med = Medication(user_id=test_user.id, name="Тестовый препарат курса", kind="medication")
    db_session.add(med)
    await db_session.flush()

    course = await svc.create_course(db_session, user_id=test_user.id, name="Тестовый курс")
    sched = await svc.create_schedule(
        db_session,
        user_id=test_user.id,
        medication_id=med.id,
        dose_quantity="1.0",
        frequency_type="daily",
        course_id=str(course.id),
    )
    await db_session.commit()

    # Сначала активен
    summary1 = await svc.schedule_summary(db_session, test_user.id)
    assert any(d["id"] == str(sched.id) for d in summary1["due"])

    # Ставим на паузу
    await svc.set_course_status(db_session, test_user.id, course.id, "paused")
    await db_session.commit()
    await db_session.refresh(sched)

    assert sched.is_active is False

    # В сводке на сегодня исчез
    summary2 = await svc.schedule_summary(db_session, test_user.id)
    assert not any(d["id"] == str(sched.id) for d in summary2["due"])

