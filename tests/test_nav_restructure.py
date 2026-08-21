"""R10.1: навигация скрывает выключенные модули по feature-флагам composition.

Гейтинг пунктов меню должен совпадать с регистрацией роутов в main.py:
medication/health/journal/care/catalog/insights/aftercare/consent_enabled,
timer_operational, social_operational.
"""
import re
import warnings

warnings.filterwarnings("ignore")  # passlib/bcrypt env artifact

import pytest
from app.platform.composition import ProductComposition, build_product_composition


async def test_nav_renders_five_sections(auth_client):
    r = await auth_client.get("/dashboard")
    assert r.status_code == 200
    titles = re.findall(r'pl-nav-group-title">([^<]+)<', r.text)
    assert len(titles) >= 5, titles
    # EN locale labels for the 5 product sections
    assert any(t in titles for t in ("Now", "Plan", "Body & Routine", "Connections", "System")), titles
    assert re.findall(r"pl-nav-item", r.text)


async def _nav_links(auth_client) -> list[tuple[str, str]]:
    r = await auth_client.get("/dashboard")
    assert r.status_code == 200
    # <a href="..." class="pl-nav-item ..."> … <span class="pl-nav-label">Label</span>
    return re.findall(r'<a href="(/[^"]+)"[^>]*class="pl-nav-item[^"]*".*?<span class="pl-nav-label">([^<]+)</span>', r.text, re.DOTALL)


async def test_nav_hides_disabled_modules(auth_client, monkeypatch):
    """Выключенные домены (medication/journal/health) не появляются в меню."""
    import app.platform.composition as comp_mod

    base = build_product_composition()
    disabled = ProductComposition(
        variant=base.variant,
        enabled_modules=base.enabled_modules,
        locktimer_core_enabled=base.locktimer_core_enabled,
        locktimer_verification_enabled=base.locktimer_verification_enabled,
        social_enabled=base.social_enabled,
        social_tracker_adapter_enabled=base.social_tracker_adapter_enabled,
        social_timer_adapter_enabled=base.social_timer_adapter_enabled,
        social_public_enabled=base.social_public_enabled,
        locktimer_keyholder_enabled=base.locktimer_keyholder_enabled,
        locktimer_cloud_media_enabled=base.locktimer_cloud_media_enabled,
        medication_enabled=False,
        health_enabled=False,
        journal_enabled=False,
        care_enabled=True,
        catalog_enabled=True,
        insights_enabled=True,
        aftercare_enabled=True,
        consent_enabled=False,
    )
    monkeypatch.setattr(comp_mod, "composition", disabled)

    links = await _nav_links(auth_client)
    hrefs = [h for h, _ in links]
    # выключенные модули скрыты
    assert "/medications" not in hrefs
    assert "/health" not in hrefs
    assert "/journal" not in hrefs
    assert "/consent/matrix" not in hrefs
    # включённые — на месте
    assert "/dashboard" in hrefs
    assert "/entities/catalog" in hrefs
    assert "/care" in hrefs
    assert "/insights/analytics" in hrefs


async def test_nav_shows_modules_when_enabled(auth_client, monkeypatch):
    """Дефолтная композиция (все домены включены) — пункты на месте."""
    import app.platform.composition as comp_mod

    monkeypatch.setattr(comp_mod, "composition", build_product_composition())
    links = await _nav_links(auth_client)
    hrefs = [h for h, _ in links]
    for h in ("/medications", "/health", "/journal", "/consent/matrix", "/entities/catalog", "/care"):
        assert h in hrefs, h
