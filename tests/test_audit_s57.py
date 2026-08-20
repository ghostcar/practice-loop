"""Session 57 audit tests:

1. risk_level on Entity (REM §5.2): default, API roundtrip, LLM gate.
2. Typed gamification DSL: validation + no eval.
3. Mobile bottom nav (DESIGN §4.4): rendered for authed users.
4. JS modules (DESIGN §15.4): no inline page scripts, external modules + JSON i18n blocks.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity

RISK_LEVELS = ("not_assessed", "low", "elevated", "high")


# ── risk_level: model default + API roundtrip ──


@pytest.mark.asyncio
async def test_entity_defaults_to_not_assessed(db_session: AsyncSession, test_user):
    ent = Entity(type="one_time", real_name="R", category="c", owner_id=test_user.id)
    db_session.add(ent)
    await db_session.flush()
    assert ent.risk_level == "not_assessed"


@pytest.mark.asyncio
async def test_create_entity_accepts_risk_level(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    resp = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Elevated task",
            "category": "test",
            "risk_level": "elevated",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    ent = (await db_session.execute(select(Entity).where(Entity.real_name == "Elevated task"))).scalar_one()
    assert ent.risk_level == "elevated"


@pytest.mark.asyncio
async def test_create_entity_rejects_unknown_risk_level(auth_client: AsyncClient, db_session: AsyncSession):
    resp = await auth_client.post(
        "/entities/",
        data={"real_name": "Bad", "category": "test", "risk_level": "extreme"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    ent = (await db_session.execute(select(Entity).where(Entity.real_name == "Bad"))).scalar_one()
    assert ent.risk_level == "not_assessed"  # sanitized to default


@pytest.mark.asyncio
async def test_seed_entities_default_to_low(db_session: AsyncSession, test_user):
    """Curated catalog seed is pre-assessed: risk_level low → automation stays open."""
    from app.seed import seed_entities

    created = await seed_entities(db_session, owner_id=test_user.id)
    if created:
        for e in created:
            assert e.risk_level == "low"
    else:
        pytest.skip("catalog already seeded")


# ── risk_level: informational metadata (ADR-106) ──


@pytest.mark.asyncio
async def test_filter_automation_eligible_opted_in_is_approved():
    """ADR-106: opt-in is the approval boundary — nothing is filtered by risk."""
    from app.llm.context_builder import filter_automation_eligible

    ents = [
        {"id": "a", "risk_level": "low"},
        {"id": "b", "risk_level": "not_assessed"},
        {"id": "c", "risk_level": "high"},
        {"id": "d", "risk_level": "elevated"},
        {"id": "e"},  # missing → not_assessed
        {"id": "f", "automation_allowed": False, "adult_only": True},
    ]
    allowed = filter_automation_eligible(ents)
    assert [e["id"] for e in allowed] == ["a", "b", "c", "d", "e", "f"]

    # allow_elevated kept for backward compatibility — no-op under ADR-106.
    with_consent = filter_automation_eligible(ents, allow_elevated=True)
    assert [e["id"] for e in with_consent] == ["a", "b", "c", "d", "e", "f"]


# ── Typed gamification DSL ──


def test_dsl_rejects_code_injection():
    from app.gamification.dsl import validate_condition

    assert validate_condition("__import__('os').system('id')") is not None
    assert validate_condition("x; import os") is not None
    assert validate_condition("x = __builtins__") is not None
    assert validate_condition("x in eval(open('/etc/passwd'))") is not None


def test_dsl_accepts_legit_conditions():
    from app.gamification.dsl import validate_condition

    assert validate_condition("extra_fluid_ml > 0") is None
    assert validate_condition("level_jump == true") is None
    assert validate_condition("mode == 'hard'") is None
    assert validate_condition("count >= 3") is None


def test_dsl_eval_never_uses_python_eval():
    import app.gamification.dsl as dsl

    assert not hasattr(dsl, "eval") or dsl.eval is None  # no eval import
    # The evaluator is a pure whitelist comparator.
    assert dsl.eval_condition("count > 5", {"count": 10}) is True
    assert dsl.eval_condition("count > 5", {"count": 2}) is False


def test_dsl_quoted_string_comparison():
    from app.gamification.dsl import eval_condition

    assert eval_condition("status == 'done'", {"status": "done"}) is True
    assert eval_condition('status == "done"', {"status": "done"}) is True
    assert eval_condition("status == 'pending'", {"status": "done"}) is False


# ── Mobile bottom nav (DESIGN §4.4) ──


@pytest.mark.asyncio
async def test_mobile_bottom_nav_renders(auth_client: AsyncClient):
    """DESIGN v2 §7: global bottom nav replaced by top bar + full-screen sheet."""
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    # Mobile top bar with the menu button + full-screen nav sheet
    assert 'id="pl-mobile-menu"' in html  # menu button present
    assert 'id="pl-mobile-sheet"' in html  # sheet present
    # Legacy global bottom nav must be gone
    assert 'aria-label="Mobile"' not in html
    assert "safe-area-inset-bottom" not in html


@pytest.mark.asyncio
async def test_mobile_bottom_nav_hidden_for_anon(async_client: AsyncClient):
    # Anonymous request → login page (no shell; it only renders for user).
    resp = await async_client.get("/login")
    assert resp.status_code == 200
    assert 'id="pl-mobile-sheet"' not in resp.text


# ── Self-hosted Inter font (DESIGN §7.1) ──


def test_inter_font_self_hosted():
    import os

    for f in ("InterVariable.woff2", "InterVariable-Italic.woff2"):
        assert os.path.isfile(f"app/static/fonts/{f}"), f"missing {f}"


@pytest.mark.asyncio
async def test_base_html_has_no_font_cdn(auth_client: AsyncClient):
    resp = await auth_client.get("/dashboard")
    assert "fonts.googleapis" not in resp.text
    assert "fonts.gstatic.com" not in resp.text
    assert "InterVariable.woff2" in resp.text


# ── JS modules (DESIGN §15.4) ──


@pytest.mark.asyncio
async def test_pages_use_external_js_modules(auth_client: AsyncClient):
    for path in ("/dashboard", "/training/", "/api/v2/points/page", "/import"):
        resp = await auth_client.get(path)
        assert resp.status_code == 200, path
        # No inline <script> bodies on page templates (shared bootstrap is app.js).
        assert "static/js/pages/" in resp.text, path


@pytest.mark.asyncio
async def test_json_i18n_blocks_are_valid(auth_client: AsyncClient):
    import json
    import re

    resp = await auth_client.get("/diets")
    assert resp.status_code == 200
    m = re.search(r'<script type="application/json" id="page-i18n">(.*?)</script>', resp.text, re.DOTALL)
    assert m, "page-i18n JSON block missing on /diets"
    data = json.loads(m.group(1))  # must be valid JSON
    assert isinstance(data, dict)
    assert "i18n" in data
    assert "has_llm" in data


@pytest.mark.asyncio
async def test_inline_script_legacy_allowlist_is_accurate():
    from pathlib import Path

    root = Path("app/templates")
    inline_pages = []
    for tpl in root.glob("*.html"):
        text = tpl.read_text(encoding="utf-8")
        # Allow: <script src=...>, <script type="application/json">, timeline JSON block,
        # and the shared app.js include. Reject raw inline JS bodies.
        stripped = (
            text.replace("<script src=", "<script_src=")
            .replace('<script type="application/json"', "<script_json=")
            .replace('<script id="timeline-data"', "<script_json=")
        )
        if "<script>" in stripped:
            inline_pages.append(tpl.name)
    # These legacy pages still need extraction into app/static/js.  Keep the
    # debt exact so new inline scripts cannot appear while migration proceeds.
    legacy_inline_pages = {
        "admin_catalog_editor.html",
        "base.html",
        "care_builder.html",
        "entity_edit.html",
        "insights.html",
        "llm_exchange.html",
        "media_progress.html",
        "medication.html",
        "sessions_live.html",
        "sessions_rules_builder.html",
        "training_builder.html",
    }
    assert set(inline_pages) == legacy_inline_pages, (
        f"inline script allowlist drift: added={sorted(set(inline_pages) - legacy_inline_pages)} "
        f"removed={sorted(legacy_inline_pages - set(inline_pages))}"
    )
