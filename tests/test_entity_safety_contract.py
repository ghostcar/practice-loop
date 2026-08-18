"""ADR-105: typed safety contract columns on Entity.

Covers model defaults (automation off, adult_only false, not_assessed, version 1),
ORM roundtrip of a populated safety contract, and the automation gate invariant.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity


@pytest.mark.asyncio
async def test_entity_safety_contract_defaults(db_session: AsyncSession, test_user):
    ent = Entity(type="one_time", real_name="R", category="c", owner_id=test_user.id)
    db_session.add(ent)
    await db_session.flush()

    assert ent.safety_contract is None
    assert ent.automation_allowed is False
    assert ent.adult_only is False
    assert ent.content_status == "not_assessed"
    assert ent.content_version == 1


@pytest.mark.asyncio
async def test_entity_safety_contract_roundtrip(db_session: AsyncSession, test_user):
    contract = {
        "eligibility": {"adult_only": True, "explicit_opt_in_required": True},
        "risk": {"level": "elevated", "automation_allowed": False},
        "safety": {"stop_conditions": ["any_participant_declines"], "checkpoints": ["confirm_continue"]},
        "evidence_policy": {"media_required": False},
    }
    ent = Entity(
        type="one_time",
        real_name="Elevated activity",
        category="c",
        owner_id=test_user.id,
        safety_contract=contract,
        automation_allowed=False,
        adult_only=True,
        content_status="reviewed",
        content_version=3,
    )
    db_session.add(ent)
    await db_session.flush()

    loaded = (await db_session.execute(select(Entity).where(Entity.id == ent.id))).scalar_one()
    assert loaded.safety_contract == contract
    assert loaded.automation_allowed is False
    assert loaded.adult_only is True
    assert loaded.content_status == "reviewed"
    assert loaded.content_version == 3


def test_schema_accepts_only_known_content_statuses():
    from pydantic import ValidationError

    from app.schemas.entity import EntityCreate

    ok = EntityCreate(real_name="x", category="c", content_status="approved")
    assert ok.content_status == "approved"

    try:
        EntityCreate(real_name="x", category="c", content_status="bogus")
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown content_status must be rejected")
