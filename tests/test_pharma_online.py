from unittest.mock import MagicMock

import pytest

from app.services.pharma_enricher import enrich_medication_info
from app.services.pharma_online import (
    _MEMORY_CACHE,
    _clean_text,
    lookup_rxnorm,
    lookup_vidal,
    online_drug_lookup,
)


@pytest.fixture(autouse=True)
def clear_pharma_cache():
    _MEMORY_CACHE.clear()
    yield
    _MEMORY_CACHE.clear()


def test_clean_text_helpers():
    assert _clean_text("<p>Нурофен&reg; <b>форте</b></p>") == "Нурофен форте"
    assert _clean_text(None) == ""
    assert _clean_text("   много   пробелов   ") == "много пробелов"


@pytest.mark.asyncio
async def test_lookup_vidal_success(monkeypatch):
    search_html = """
    <table class="products-table">
      <tr>
        <td class="products-table-name">
          <a href="/drugs/nurofen">Нурофен&reg;</a>
        </td>
      </tr>
    </table>
    """
    drug_html = """
    <h1>Нурофен</h1>
    <div class="hyphenate"><p>таблетки, покрытые оболочкой 200 мг</p></div>
    <a href="/drugs/molecule/524">ибупрофен</a>
    <a href="/drugs/firm/123">Reckitt Benckiser</a>
    """
    molecule_html = """
    <td class="products-table-name"><a href="/drugs/mig_400">МИГ 400</a></td>
    <td class="products-table-name"><a href="/drugs/faspic">Фаспик</a></td>
    """

    async def mock_get(self, url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "search" in url:
            resp.text = search_html
        elif "/drugs/molecule-in/" in url:
            resp.text = molecule_html
        else:
            resp.text = drug_html
        return resp

    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)

    res = await lookup_vidal("нурофен")
    assert res is not None
    assert res["name"] == "Нурофен"
    assert res["active_ingredient"] == "Ибупрофен"
    assert res["manufacturer"] == "Reckitt Benckiser"
    assert "таблетки" in res["form"]
    assert len(res["analogs"]) >= 2
    analog_names = [a["name"] for a in res["analogs"]]
    assert "МИГ 400" in analog_names
    assert "Фаспик" in analog_names


@pytest.mark.asyncio
async def test_lookup_vidal_network_error_handled(monkeypatch):
    async def failing_get(self, url, **kwargs):
        raise ConnectionError("Network unreachable")

    monkeypatch.setattr("httpx.AsyncClient.get", failing_get)

    res = await lookup_vidal("любой_препарат")
    assert res is None


@pytest.mark.asyncio
async def test_lookup_rxnorm_success(monkeypatch):
    rxnorm_data = {
        "drugGroup": {
            "conceptGroup": [
                {
                    "conceptProperties": [
                        {"name": "Ibuprofen 200 MG Oral Tablet"},
                        {"name": "Ibuprofen 400 MG Oral Tablet"},
                        {"name": "Advil 200 MG Oral Tablet"},
                    ]
                }
            ]
        }
    }

    async def mock_get(self, url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value=rxnorm_data)
        return resp

    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)

    res = await lookup_rxnorm("ibuprofen")
    assert res is not None
    assert res["name"] == "Ibuprofen 200 MG Oral Tablet"
    assert res["active_ingredient"] == "Ibuprofen"
    assert len(res["analogs"]) >= 2


@pytest.mark.asyncio
async def test_online_drug_lookup_fallback(monkeypatch):
    async def mock_vidal(name, **kwargs):
        return None

    async def mock_rxnorm(name):
        return {"name": "Paracetamol 500mg", "kind": "medication"}

    monkeypatch.setattr("app.services.pharma_online.lookup_vidal", mock_vidal)
    monkeypatch.setattr("app.services.pharma_online.lookup_rxnorm", mock_rxnorm)

    res = await online_drug_lookup("paracetamol")
    assert res is not None
    assert res["name"] == "Paracetamol 500mg"


@pytest.mark.asyncio
async def test_enrich_medication_info_prioritizes_seed_then_online(db_session, test_user, monkeypatch):
    # Препарат из seed
    res_seed = await enrich_medication_info(db_session, test_user.id, "Но-шпа")
    assert res_seed is not None
    assert "Дротаверин" in [c["name"] for c in res_seed.get("components", [])]

    # Препарат не из seed -> пробует онлайн
    async def mock_online(name, **kwargs):
        return {
            "name": name,
            "kind": "medication",
            "form": "таблетки",
            "components": [{"name": "Тестовое вещество", "inn": "Test inn"}],
        }

    monkeypatch.setattr("app.services.pharma_online.online_drug_lookup", mock_online)
    res_online = await enrich_medication_info(db_session, test_user.id, "РедкийПрепарат123")
    assert res_online is not None
    assert res_online["form"] == "таблетки"
    assert res_online["components"][0]["name"] == "Тестовое вещество"
