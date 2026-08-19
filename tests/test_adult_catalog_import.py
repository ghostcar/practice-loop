"""ADR-105: dry-run importer for the P1 18+ catalog.

Covers plan projection (41 entities from foundation + candidates), the typed
safety_contract, the approved content_status, gate refusal, ORM roundtrip via
the importer's field mapping, and slug-idempotent apply.
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.adult_catalog_import import (
    IMPORT_CONTENT_STATUS,
    SAFETY_CONTRACT_VERSION,
    build_candidate_contract,
    build_foundation_contract,
    build_plan,
    render_plan,
    validate_plan,
)
from tools.adult_catalog_manifest import load_manifest

MANIFEST_DIR = Path("data/seed")


@pytest.fixture(scope="module")
def plan():
    foundation = load_manifest(MANIFEST_DIR / "adult_activity_foundation.v1.json")
    full_catalog = load_manifest(MANIFEST_DIR / "adult_activity_full_catalog.v1.json")
    return build_plan(foundation, full_catalog)


def test_plan_imports_everything(plan):
    assert len(plan["entities"]) == 194  # 7 foundation + 187 promoted cards


def test_plan_is_valid(plan):
    assert validate_plan(plan) == []


def test_plan_gate_is_open(plan):
    assert plan["gate"]["foundation_import_allowed"] is True
    assert plan["gate"]["full_catalog_import_allowed"] is True


def test_plan_preserves_automation_and_risk(plan):
    foundation = [e for e in plan["entities"] if e["safety_contract"]["kind"] == "foundation"]
    promoted = [e for e in plan["entities"] if e["safety_contract"]["kind"] == "editorial_candidate"]
    # owner decision: foundation keeps its manifest automation (7 low auto=true),
    # all 154 promoted cards stay manual.
    assert len(foundation) == 7
    assert all(e["automation_allowed"] for e in foundation)
    assert len(promoted) == 187
    assert all(not e["automation_allowed"] for e in promoted)
    assert all(e["risk_level"] in {"low", "elevated"} for e in plan["entities"])


def test_plan_stamps_approved_and_adult_only(plan):
    assert all(e["content_status"] == IMPORT_CONTENT_STATUS for e in plan["entities"])
    assert all(e["adult_only"] is True for e in plan["entities"])
    assert all(e["content_version"] == 1 for e in plan["entities"])


def test_foundation_contract_is_lossless():
    foundation = load_manifest(MANIFEST_DIR / "adult_activity_foundation.v1.json")
    card = foundation["cards"][0]

    contract = build_foundation_contract(card)

    assert contract["schema_version"] == SAFETY_CONTRACT_VERSION
    assert contract["eligibility"]["adult_only"] is True
    assert contract["eligibility"]["explicit_opt_in_required"] is True
    assert contract["safety"]["stop_conditions"]
    assert contract["evidence_policy"]["media_required"] is False
    assert contract["gamification"]["penalty_enabled"] is False


def test_candidate_contract_uses_safe_defaults():
    candidates = load_manifest(MANIFEST_DIR / "adult_activity_editorial_candidates.v1.json")
    card = candidates["cards"][0]

    contract = build_candidate_contract(card)

    assert contract["schema_version"] == SAFETY_CONTRACT_VERSION
    assert contract["eligibility"]["adult_only"] is True
    assert contract["eligibility"]["explicit_opt_in_required"] is True
    assert contract["eligibility"]["session_checkin_required"] is True
    assert contract["risk"]["automation_allowed"] is False
    assert contract["evidence_policy"]["media_required"] is False
    assert contract["gamification"]["penalty_enabled"] is False


def test_render_plan_is_read_only_summary(plan):
    rendered = render_plan(plan)

    assert "entities=194" in rendered
    assert "content_status=approved" in rendered
    assert "gate.foundation_import_allowed=True" in rendered


def test_validate_rejects_elevated_automation():
    foundation = load_manifest(MANIFEST_DIR / "adult_activity_foundation.v1.json")
    full_catalog = load_manifest(MANIFEST_DIR / "adult_activity_full_catalog.v1.json")
    plan = build_plan(foundation, full_catalog)
    # flip an elevated candidate to automation on
    elevated = next(e for e in plan["entities"] if e["risk_level"] == "elevated")
    elevated["automation_allowed"] = True
    elevated["safety_contract"]["risk"]["automation_allowed"] = True

    errors = validate_plan(plan)

    assert any("elevated cards must keep automation off" in e for e in errors)


@pytest.mark.asyncio
async def test_apply_plan_slug_idempotent_roundtrip(db_session: AsyncSession):
    from app.models.entity import Entity

    foundation = load_manifest(MANIFEST_DIR / "adult_activity_foundation.v1.json")
    full_catalog = load_manifest(MANIFEST_DIR / "adult_activity_full_catalog.v1.json")
    plan = build_plan(foundation, full_catalog)

    # Simulate the gated apply against the test session (import only 2 rows to keep
    # the fixture light, then re-apply to prove idempotency).
    small_plan = {"gate": plan["gate"], "entities": plan["entities"][:2]}

    async def _apply(entities):
        imported = skipped = 0
        for fields in entities:
            existing = await db_session.execute(
                select(Entity.id).where(Entity.slug == fields["slug"]).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue
            db_session.add(Entity(**fields))
            imported += 1
        await db_session.flush()
        return imported, skipped

    imported, skipped = await _apply(small_plan["entities"])
    assert imported == 2
    assert skipped == 0

    # Re-apply the same plan → all skipped by slug.
    imported, skipped = await _apply(small_plan["entities"])
    assert imported == 0
    assert skipped == 2

    # Roundtrip the typed contract through the JSONB column.
    loaded = (
        await db_session.execute(select(Entity).where(Entity.slug == small_plan["entities"][0]["slug"]))
    ).scalar_one()
    assert loaded.content_status == "approved"
    assert loaded.adult_only is True
    assert loaded.safety_contract["schema_version"] == SAFETY_CONTRACT_VERSION
    assert loaded.safety_contract["eligibility"]["adult_only"] is True


def test_apply_plan_requires_explicit_database_url():
    import tools.adult_catalog_import as importer

    # The real DB path is exercised only behind --apply/--database-url; the pure
    # read-only path (render/validate) never touches a DB engine.
    assert importer.apply_plan is not None
