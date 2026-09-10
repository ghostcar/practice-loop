"""Tests for multicomponent medication analogs and online catalogs lookup."""

from __future__ import annotations

import json

import pytest

from app.models.medication import Medication
from app.services.med.substances import extract_med_substances
from app.services.med_service import find_analogs, med_dict


def test_extract_med_substances_from_string():
    """Тест извлечения компонентов из строки active_ingredient."""
    class FakeMed:
        components = []
        active_ingredient = "эстрадиол 2 мг + дидрогестерон 10 мг"

    subs = extract_med_substances(FakeMed())
    assert subs == ["Эстрадиол", "Дидрогестерон"]

    # Другие разделители и дозировки
    class FakeMed2:
        components = []
        active_ingredient = "Амоксициллин 500мг, клавулановая кислота 125мг"

    subs2 = extract_med_substances(FakeMed2())
    assert subs2 == ["Амоксициллин", "Клавулановая кислота"]


@pytest.mark.asyncio
async def test_med_dict_includes_available_substances(db_session, test_user):
    """med_dict возвращает available_substances для фронтенда."""
    m = Medication(
        user_id=test_user.id,
        name="Фемостон 2/10",
        kind="medication",
        active_ingredient="эстрадиол 2 мг + дидрогестерон 10 мг",
    )
    db_session.add(m)
    await db_session.flush()

    d = med_dict(m)
    assert "available_substances" in d
    assert d["available_substances"] == ["Эстрадиол", "Дидрогестерон"]


@pytest.mark.asyncio
async def test_find_analogs_with_target_substance(db_session, test_user, monkeypatch):
    """Поиск аналогов по конкретному компоненту многокомпонентного препарата."""
    m = Medication(
        user_id=test_user.id,
        name="Фемостон 2/10",
        kind="medication",
        active_ingredient="эстрадиол 2 мг + дидрогестерон 10 мг",
    )
    db_session.add(m)
    await db_session.flush()

    from app.models.llm_config import LLMProviderConfig
    cfg = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="Omniroute",
        api_base_url="http://mock-llm/v1",
        model_name="auto",
        is_active=True,
    )
    db_session.add(cfg)
    await db_session.flush()

    captured_prompt = {}

    async def mock_call_llm(config, system_prompt, user_message, **kwargs):
        captured_prompt["system"] = system_prompt
        captured_prompt["user"] = user_message
        return {
            "content": json.dumps({
                "summary": "Аналоги эстрадиола",
                "analogs": [
                    {
                        "name": "Эстрожель",
                        "manufacturer": "Besins",
                        "form": "гель",
                        "strength": "0.06%",
                        "same_composition": False,
                        "notes": "Монопрепарат эстрадиола",
                    }
                ],
            }),
            "usage": {"total_tokens": 50},
        }

    from app.llm import client as llm_client
    monkeypatch.setattr(llm_client, "call_llm", mock_call_llm)

    res = await find_analogs(
        db_session,
        test_user.id,
        m.id,
        target_substance="Эстрадиол",
        source_type="llm",
    )

    assert res["target_substance"] == "Эстрадиол"
    assert "Эстрадиол" in captured_prompt["system"]
    assert len(res["analogs"]) == 1
    assert res["analogs"][0]["name"] == "Эстрожель"
    assert res["analogs"][0]["notes"] == "Монопрепарат эстрадиола"


@pytest.mark.asyncio
async def test_find_analogs_online_directory_only(db_session, test_user, monkeypatch):
    """Поиск аналогов только по онлайн-каталогам (без вызова LLM)."""
    m = Medication(
        user_id=test_user.id,
        name="Фемостон 2/10",
        kind="medication",
        active_ingredient="эстрадиол 2 мг + дидрогестерон 10 мг",
    )
    db_session.add(m)
    await db_session.flush()

    from app.services import pharma_online

    async def mock_online_lookup(name, max_analogs=10, target_substance=None, target_strength=None, **kwargs):
        return {
            "source": "vidal.ru",
            "analogs": [
                {
                    "name": "Климонорм",
                    "manufacturer": "Bayer",
                    "form": "драже",
                    "strength": "2 мг",
                    "same_composition": False,
                    "notes": "Каталог Vidal",
                }
            ],
        }

    monkeypatch.setattr(pharma_online, "online_drug_lookup", mock_online_lookup)

    res = await find_analogs(
        db_session,
        test_user.id,
        m.id,
        source_type="online",
    )

    assert res["source"] == "vidal.ru"
    assert len(res["analogs"]) == 1
    assert res["analogs"][0]["name"] == "Климонорм"


@pytest.mark.asyncio
async def test_find_analogs_html_form_and_json_api(auth_client, test_user, db_session, monkeypatch):
    """Проверка работы веб-формы и JSON API с target_substance и source_type."""
    m = Medication(
        user_id=test_user.id,
        name="Фемостон 2/10",
        kind="medication",
        active_ingredient="эстрадиол 2 мг + дидрогестерон 10 мг",
    )
    db_session.add(m)
    await db_session.flush()

    from app.services import pharma_online

    async def mock_online_lookup(name, max_analogs=10, target_substance=None, target_strength=None, **kwargs):
        return {
            "source": "vidal.ru",
            "analogs": [
                {
                    "name": "Дивигель",
                    "manufacturer": "Orion",
                    "form": "гель",
                    "strength": "1 мг",
                    "same_composition": False,
                    "notes": f"Vidal online (target={target_substance})",
                }
            ],
        }

    monkeypatch.setattr(pharma_online, "online_drug_lookup", mock_online_lookup)

    # 1. HTML Form handler: POST /medications/{id}/find-analogs
    resp = await auth_client.post(
        f"/medications/{m.id}/find-analogs",
        data={
            "target_substance": "Эстрадиол",
            "source_type": "online",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "analogs_done=1" in resp.headers["location"]

    # Check updated medication in db
    await db_session.refresh(m)
    assert m.analogues is not None
    assert m.analogues["target_substance"] == "Эстрадиол"
    assert m.analogues["source"] == "vidal.ru"
    assert m.analogues["analogs"][0]["name"] == "Дивигель"

    # 2. JSON API handler: POST /api/v2/medications/{id}/analogs
    resp2 = await auth_client.post(
        f"/api/v2/medications/{m.id}/analogs",
        json={
            "target_substance": "Дидрогестерон",
            "source_type": "online",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()["analogues"]
    assert data2["target_substance"] == "Дидрогестерон"
    assert data2["analogs"][0]["notes"] == "Vidal online (target=Дидрогестерон)"


def test_pharma_dosage_helpers():
    """Тестирование извлечения и нормализации дозировок из названий лекарств."""
    from app.services.pharma_online import (
        clean_drug_name,
        extract_dosage_strength,
        normalize_strength_val_unit,
        strengths_match,
    )

    # clean_drug_name
    assert clean_drug_name("Верошпирон 25 мг") == "Верошпирон"
    assert clean_drug_name("Праджисан 100 мг") == "Праджисан"
    assert clean_drug_name("Фемостон 2/10") == "Фемостон"
    assert clean_drug_name("Амоксиклав 500 мг + 125 мг таб.") == "Амоксиклав"

    # extract_dosage_strength
    assert extract_dosage_strength("Верошпирон 25 мг") == "25 мг"
    assert extract_dosage_strength("Праджисан", "200 мг") == "200 мг"
    assert extract_dosage_strength("Фемостон", "2 мг + 10 мг") == "2 мг + 10 мг"

    # normalize_strength_val_unit
    assert normalize_strength_val_unit("25 мг") == (25.0, "мг")
    assert normalize_strength_val_unit("0.06%") == (0.06, "%")

    # strengths_match
    assert strengths_match("25 мг", ["25 мг", "50 мг", "100 мг"]) is True
    assert strengths_match("50 мг", "25 мг, 50 мг, 100 мг") is True
    assert strengths_match("200 мг", ["100 мг", "200 мг"]) is True
    assert strengths_match("200 мг", ["90 мг"]) is False


@pytest.mark.asyncio
async def test_find_analogs_verospiron_dosage_matching(db_session, test_user, monkeypatch):
    """Тест поиска аналогов для Верошпирона 25 мг с проверкой совпадения дозировок."""
    m = Medication(
        user_id=test_user.id,
        name="Верошпирон 25 мг",
        kind="medication",
        active_ingredient="Спиронолактон",
        strength="25 мг",
    )
    db_session.add(m)
    await db_session.flush()

    from app.services import pharma_online

    async def mock_online_lookup(name, max_analogs=10, target_substance=None, target_strength=None):
        return {
            "source": "vidal.ru",
            "analogs": [
                {
                    "name": "Верошпилактон",
                    "manufacturer": "ФАРМСТАНДАРТ",
                    "form": "таблетки",
                    "strength": "25 мг, 50 мг, 100 мг",
                    "same_composition": True,
                    "same_strength": True,
                    "notes": "Совпадает дозировка (25 мг). Доступно: 25 мг, 50 мг, 100 мг",
                },
                {
                    "name": "Спиронолактон Канон",
                    "manufacturer": "КАНОНФАРМА",
                    "form": "капсулы",
                    "strength": "50 мг, 100 мг",
                    "same_composition": True,
                    "same_strength": False,
                    "notes": "Доступно: 50 мг, 100 мг",
                },
            ],
        }

    monkeypatch.setattr(pharma_online, "online_drug_lookup", mock_online_lookup)

    res = await find_analogs(
        db_session,
        test_user.id,
        m.id,
        source_type="online",
        target_strength="25 мг",
    )

    assert res["target_strength"] == "25 мг"
    analogs = res["analogs"]
    assert len(analogs) == 2
    assert analogs[0]["name"] == "Верошпилактон"
    assert analogs[0]["same_strength"] is True
    assert analogs[1]["name"] == "Спиронолактон Канон"
    assert analogs[1]["same_strength"] is False


@pytest.mark.asyncio
async def test_find_analogs_prajisan_dosage_matching(db_session, test_user, monkeypatch):
    """Тест поиска аналогов для Праджисана (200 мг) с сопоставлением капсул и геля."""
    m = Medication(
        user_id=test_user.id,
        name="Праджисан",
        kind="medication",
        active_ingredient="Прогестерон",
        strength="200 мг",
    )
    db_session.add(m)
    await db_session.flush()

    from app.services import pharma_online

    async def mock_online_lookup(name, max_analogs=10, target_substance=None, target_strength=None):
        return {
            "source": "vidal.ru",
            "analogs": [
                {
                    "name": "Утрожестан",
                    "manufacturer": "Besins",
                    "form": "капсулы",
                    "strength": "100 мг, 200 мг",
                    "same_composition": True,
                    "notes": "Капсулы 100 мг, 200 мг",
                },
                {
                    "name": "Крайнон",
                    "manufacturer": "Merck",
                    "form": "гель вагинальный",
                    "strength": "90 мг/доза",
                    "same_composition": True,
                    "notes": "Гель 90 мг",
                },
            ],
        }

    monkeypatch.setattr(pharma_online, "online_drug_lookup", mock_online_lookup)

    res = await find_analogs(
        db_session,
        test_user.id,
        m.id,
        source_type="online",
        target_strength="200 мг",
    )

    assert res["target_strength"] == "200 мг"
    analogs = res["analogs"]
    assert len(analogs) == 2
    # Утрожестан имеет 200 мг -> same_strength=True
    utro = next(a for a in analogs if a["name"] == "Утрожестан")
    assert utro["same_strength"] is True
    # Крайнон 90 мг -> same_strength=False
    cray = next(a for a in analogs if a["name"] == "Крайнон")
    assert cray["same_strength"] is False

