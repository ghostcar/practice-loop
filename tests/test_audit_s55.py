"""Tests for Session 55 audit fixes.

Covers: diet LLM generation/evaluation + consumptions API, llm-config mode
toggles, atomic complete (interrupted can't complete), /points/balance
cross-user isolation, canonical entity_name in the pipeline, GET / landing.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.diet import Diet, DietConsumption, DietItem, DietTrainingReview
from app.models.entity import Entity
from app.models.llm_config import LLMProviderConfig
from app.models.training import TrainingDay


def _llm_cfg(db, user, mode="full", store_raw=True) -> LLMProviderConfig:
    cfg = LLMProviderConfig(
        user_id=user.id,
        provider_name="test",
        api_base_url="http://test",
        api_key_encrypted="encrypted-key",
        model_name="m",
        is_active=True,
        llm_mode=mode,
        store_raw_response=store_raw,
    )
    db.add(cfg)
    return cfg


# ── Diets: consumption (fact) API ──


@pytest.mark.asyncio
async def test_consumption_crud(auth_client, db_session, test_user):
    # create
    res = await auth_client.post(
        "/diets/api/consumptions",
        json={"name": "Oatmeal", "quantity": 100, "unit": "g", "meal_time": "breakfast"},
    )
    assert res.status_code == 200
    c = res.json()
    assert c["name"] == "Oatmeal"
    assert c["consumed_date"] == date.today().isoformat()

    # list (today)
    res = await auth_client.get("/diets/api/consumptions")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # list filtered by a past date → empty
    res = await auth_client.get("/diets/api/consumptions", params={"consumed_date": "2020-01-01"})
    assert res.json() == []

    # delete
    res = await auth_client.delete(f"/diets/api/consumptions/{c['id']}")
    assert res.status_code == 200
    res = await auth_client.get("/diets/api/consumptions")
    assert res.json() == []


@pytest.mark.asyncio
async def test_consumption_rejects_foreign_diet(auth_client, db_session, test_user):
    other_diet = Diet(user_id=uuid.uuid4(), name="Other")
    db_session.add(other_diet)
    await db_session.flush()

    res = await auth_client.post(
        "/diets/api/consumptions",
        json={"name": "X", "diet_id": str(other_diet.id)},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_consumption_cross_user_delete(auth_client, db_session, test_user):
    other = DietConsumption(user_id=uuid.uuid4(), name="Other", consumed_date=date.today())
    db_session.add(other)
    await db_session.flush()

    res = await auth_client.delete(f"/diets/api/consumptions/{other.id}")
    assert res.status_code == 404


# ── Diets: LLM generation ──


@pytest.mark.asyncio
async def test_diet_llm_generate(db_session, test_user):
    from app.llm.pipeline import generate_diet

    cfg = _llm_cfg(db_session, test_user)
    await db_session.flush()

    payload = {
        "name": "Protein Lean",
        "description": "High-protein plan",
        "items": [
            {"name": "Chicken breast", "quantity": 200, "unit": "g", "meal_time": "lunch", "notes": ""},
            {"name": "Cottage cheese", "quantity": 150, "unit": "g", "meal_time": "dinner", "notes": ""},
        ],
    }
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        diet = await generate_diet(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            locale="en",
            direction="muscle_gain",
            goal="Gain mass",
        )
    assert diet.name == "Protein Lean"
    assert diet.direction == "muscle_gain"
    items_result = await db_session.execute(
        select(DietItem).where(DietItem.diet_id == diet.id).order_by(DietItem.sort_order)
    )
    items = items_result.scalars().all()
    assert len(items) == 2
    assert items[0].sort_order == 0


@pytest.mark.asyncio
async def test_diet_llm_generate_rejects_empty(db_session, test_user):
    from app.llm.pipeline import generate_diet

    cfg = _llm_cfg(db_session, test_user)
    await db_session.flush()

    with (
        patch(
            "app.llm.client.call_llm",
            new=AsyncMock(
                return_value={
                    "content": json.dumps({"name": "Empty", "items": []}),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
                }
            ),
        ),
        pytest.raises(ValueError),
    ):
        await generate_diet(db=db_session, user_id=test_user.id, llm_config=cfg, locale="en")


@pytest.mark.asyncio
async def test_diet_llm_generate_endpoint(auth_client, db_session, test_user):
    _llm_cfg(db_session, test_user)
    await db_session.flush()

    payload = {
        "name": "AI Diet",
        "description": "d",
        "items": [{"name": "Eggs", "quantity": 2, "unit": "pcs", "meal_time": "breakfast"}],
    }
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        res = await auth_client.post("/diets/api/generate", json={"direction": "health", "goal": "Feel good"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "AI Diet"
    assert body["direction"] == "health"


@pytest.mark.asyncio
async def test_diet_llm_generate_requires_active_config(auth_client, db_session, test_user):
    res = await auth_client.post("/diets/api/generate", json={"goal": "x"})
    assert res.status_code == 400


# ── Diets: LLM evaluation + adjustments ──


@pytest.mark.asyncio
async def test_diet_llm_evaluate_applies_adjustments(db_session, test_user):
    from app.llm.pipeline import evaluate_diet

    cfg = _llm_cfg(db_session, test_user)
    diet = Diet(user_id=test_user.id, name="Keto", direction="weight_loss", is_active=True)
    db_session.add(diet)
    await db_session.flush()
    item = DietItem(diet_id=diet.id, name="Eggs", quantity=2, unit="pcs", sort_order=0)
    db_session.add(item)
    db_session.add(
        DietConsumption(
            user_id=test_user.id,
            diet_id=diet.id,
            name="Pizza",
            quantity=300,
            unit="g",
            consumed_date=date.today(),
        )
    )
    await db_session.flush()

    payload = {
        "score": 65,
        "summary": "Decent adherence, too many carbs.",
        "findings": ["Pizza twice this week", "Great on protein"],
        "adjustments": [
            {"action": "add", "name": "Salmon", "quantity": 150, "unit": "g", "meal_time": "dinner"},
            {"action": "modify", "match_name": "Eggs", "quantity": 3},
            {"action": "remove", "match_name": "Sugar"},
        ],
    }
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        evaluation = await evaluate_diet(db=db_session, diet=diet, llm_config=cfg, locale="en", days=7)

    assert evaluation["score"] == 65
    assert len(evaluation["findings"]) == 2
    applied = {a["action"] for a in evaluation["applied"]}
    assert applied == {"add", "modify"}
    # "Sugar" wasn't in the plan → remove silently skipped
    assert len(evaluation["applied"]) == 2

    await db_session.refresh(diet)
    assert diet.last_evaluation is not None
    assert diet.evaluated_at is not None
    # new item added, old item quantity modified
    items_result = await db_session.execute(select(DietItem).where(DietItem.diet_id == diet.id))
    items = items_result.scalars().all()
    names = [i.name for i in items]
    assert "Salmon" in names
    eggs = next(i for i in items if i.name == "Eggs")
    assert eggs.quantity == 3


@pytest.mark.asyncio
async def test_diet_llm_evaluate_endpoint(auth_client, db_session, test_user):
    _llm_cfg(db_session, test_user)
    diet = Diet(user_id=test_user.id, name="Keto")
    db_session.add(diet)
    await db_session.flush()
    db_session.add(DietConsumption(user_id=test_user.id, diet_id=diet.id, name="Eggs", consumed_date=date.today()))
    await db_session.flush()

    payload = {"score": 80, "summary": "Good", "findings": [], "adjustments": []}
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        res = await auth_client.post(f"/diets/api/{diet.id}/evaluate", json={"days": 7})
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation"]["score"] == 80
    assert body["diet"]["last_evaluation"]["score"] == 80


# ── llm-configs: mode toggles ──


@pytest.mark.asyncio
async def test_llm_config_update_toggles_mode(auth_client, db_session, test_user):
    cfg = _llm_cfg(db_session, test_user, mode="full", store_raw=True)
    await db_session.flush()

    res = await auth_client.post(f"/llm-configs/{cfg.id}/update", data={"llm_mode": "abstract"})
    assert res.status_code == 303
    await db_session.refresh(cfg)
    assert cfg.llm_mode == "abstract"
    # checkbox absent → store_raw_response False
    assert cfg.store_raw_response is False


@pytest.mark.asyncio
async def test_llm_config_update_cross_user(auth_client, db_session, test_user):
    other = LLMProviderConfig(user_id=uuid.uuid4(), provider_name="o", api_base_url="u", model_name="m")
    db_session.add(other)
    await db_session.flush()

    res = await auth_client.post(f"/llm-configs/{other.id}/update", data={"llm_mode": "abstract"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_llm_config_create_accepts_mode(auth_client, db_session, test_user, monkeypatch):
    async def connection_ok(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.llm_configs.check_llm_connection", connection_ok)
    await auth_client.post(
        "/api/v2/consent",
        json={"consent_type": "byok_provider", "state": "granted"},
    )
    res = await auth_client.post(
        "/llm-configs/",
        data={
            "provider_name": "P",
            "api_base_url": "http://x",
            "model_name": "m",
            "llm_mode": "abstract",
            "store_raw_response": "false",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    from sqlalchemy import select

    result = await db_session.execute(select(LLMProviderConfig).where(LLMProviderConfig.user_id == test_user.id))
    cfg = result.scalar_one()
    assert cfg.llm_mode == "abstract"
    assert cfg.store_raw_response is False


# ── Atomic complete: interrupted task cannot be completed ──


@pytest.mark.asyncio
async def test_interrupted_training_task_cannot_complete(auth_client, db_session, test_user):
    """Audit: an interrupted task must not be completable for XP/points."""
    ent = Entity(type="one_time", real_name="Task", category="fitness", owner_id=test_user.id)
    db_session.add(ent)
    await db_session.flush()
    log = ActivityLog(
        user_id=test_user.id,
        entity_id=ent.id,
        status="stopped",
        selected_entity_name="Task",
    )
    db_session.add(log)
    await db_session.flush()

    res = await auth_client.post(f"/training/tasks/{log.id}/complete", follow_redirects=False)
    # The endpoint redirects regardless; verify via DB that status unchanged
    assert res.status_code == 303
    await db_session.refresh(log)
    assert log.status == "stopped"
    assert log.completed_at is None


# ── /points/balance cross-user isolation ──


@pytest.mark.asyncio
async def test_points_balance_hides_foreign_thresholds(auth_client, db_session, test_user):
    """User A must not see private thresholds of user B's entity."""
    from app.models.points import PointsProfile

    profile = PointsProfile(
        user_id=uuid.uuid4(),
        name="Secret",
        config={
            "points": {"base": 10},
            "penalties": {"enabled": True},
            "bonuses": [],
            "thresholds": {"negative": -100, "warning": 0, "good": 100},
        },
    )
    db_session.add(profile)
    await db_session.flush()

    res = await auth_client.get("/api/v2/points/balance")
    assert res.status_code == 200
    assert "Secret" not in json.dumps(res.json())


# ── Landing page ──


@pytest.mark.asyncio
async def test_home_page_no_500(async_client):
    """GET / must render the landing page for anonymous users (audit: 500)."""
    res = await async_client.get("/", follow_redirects=False)
    assert res.status_code == 200


# ── Pipeline: canonical entity name ──


@pytest.mark.asyncio
async def test_generate_task_uses_canonical_entity_name(db_session, test_user):
    """The LLM-supplied entity_name must be replaced with the server-side one."""
    from app.llm.pipeline import generate_task

    cfg = _llm_cfg(db_session, test_user)
    ent = Entity(
        type="one_time",
        real_name="Real Name",
        category="fitness",
        owner_id=test_user.id,
        risk_level="low",
    )
    db_session.add(ent)
    await db_session.flush()

    full_context = {
        "allowed_entities": [
            {
                "id": str(ent.id),
                "name": "Real Name",
                "type": "one_time",
                "category": "fitness",
                "params_schema": None,
                "desire_level": "want",
                "intensity": "active",
                "risk_level": "low",
            }
        ],
        "stats": {"total_activities": 0, "completed": 0, "stopped": 0, "week_activities": 0},
        "recent_history": [],
        "active_penalties": [],
        "calendar_schedule": None,
        "locale": "en",
    }
    payload = {
        "entity_id": str(ent.id),
        "entity_name": "FAKE NAME FROM LLM",
        "params": {},
        "reasoning": "r",
    }
    with (
        patch("app.llm.context_builder.build_context", new=AsyncMock(return_value=full_context)),
        patch(
            "app.llm.client.call_llm",
            new=AsyncMock(
                return_value={
                    "content": json.dumps(payload),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
                }
            ),
        ),
    ):
        log = await generate_task(db=db_session, user_id=test_user.id, llm_config=cfg, locale="en")
    assert log.selected_entity_name == "Real Name"


# ── Diets: evaluation history + synergy ──


@pytest.mark.asyncio
async def test_evaluation_history_persisted(auth_client, db_session, test_user):
    """Every evaluate run appends to diet_evaluations (history over time)."""
    _llm_cfg(db_session, test_user)
    diet = Diet(user_id=test_user.id, name="Keto")
    db_session.add(diet)
    await db_session.flush()

    payload = {"score": 60, "summary": "First", "findings": [], "adjustments": []}
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        res = await auth_client.post(f"/diets/api/{diet.id}/evaluate", json={"days": 7})
        assert res.status_code == 200

    res = await auth_client.get(f"/diets/api/{diet.id}/evaluations")
    assert res.status_code == 200
    history = res.json()
    assert len(history) == 1
    assert history[0]["score"] == 60
    assert history[0]["summary"] == "First"

    # Second run appends, newest first
    payload2 = {"score": 80, "summary": "Second", "findings": [], "adjustments": []}
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload2),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        res = await auth_client.post(f"/diets/api/{diet.id}/evaluate", json={"days": 7})
        assert res.status_code == 200
    res = await auth_client.get(f"/diets/api/{diet.id}/evaluations")
    history = res.json()
    assert len(history) == 2
    assert history[0]["summary"] == "Second"


@pytest.mark.asyncio
async def test_evaluation_history_cross_user(auth_client, db_session, test_user):
    other = Diet(user_id=uuid.uuid4(), name="Other")
    db_session.add(other)
    await db_session.flush()

    res = await auth_client.get(f"/diets/api/{other.id}/evaluations")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_diet_training_synergy(db_session, test_user):
    from app.llm.pipeline import analyze_diet_training_synergy

    cfg = _llm_cfg(db_session, test_user)
    diet = Diet(user_id=test_user.id, name="Keto", direction="weight_loss", is_active=True)
    db_session.add(diet)
    await db_session.flush()
    db_session.add(
        DietConsumption(
            user_id=test_user.id, diet_id=diet.id, name="Oats", quantity=80, unit="g", consumed_date=date.today()
        )
    )
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()
    await db_session.flush()

    payload = {
        "summary": "Carbs on training days help.",
        "correlations": [
            {"direction": "diet_to_training", "text": "Higher carbs → more completed tasks"},
            {"direction": "training_to_diet", "text": "Heavy days → more snacks"},
        ],
        "adjustments": ["Add a pre-workout snack on training days"],
    }
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        review = await analyze_diet_training_synergy(
            db=db_session, user_id=test_user.id, llm_config=cfg, locale="en", days=7
        )
    assert review.analysis["summary"] == "Carbs on training days help."
    assert len(review.analysis["correlations"]) == 2
    assert len(review.analysis["adjustments"]) == 1
    assert review.period_end == date.today()

    result = await db_session.execute(select(DietTrainingReview).where(DietTrainingReview.user_id == test_user.id))
    assert result.scalars().all()[0].id == review.id


@pytest.mark.asyncio
async def test_synergy_endpoint_requires_llm(auth_client, db_session, test_user):
    res = await auth_client.post("/diets/api/synergy", json={"days": 7})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_synergy_endpoint_and_list(auth_client, db_session, test_user):
    _llm_cfg(db_session, test_user)
    await db_session.flush()

    payload = {"summary": "S", "correlations": [], "adjustments": []}
    with patch(
        "app.llm.client.call_llm",
        new=AsyncMock(
            return_value={
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            }
        ),
    ):
        res = await auth_client.post("/diets/api/synergy", json={"days": 7})
    assert res.status_code == 200
    review = res.json()
    assert review["analysis"]["summary"] == "S"

    res = await auth_client.get("/diets/api/synergy")
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_diet_item_inline_update(auth_client, db_session, test_user):
    """Inline edit of a diet item via PUT (name/qty/unit/meal/notes)."""
    diet = Diet(user_id=test_user.id, name="Keto")
    db_session.add(diet)
    await db_session.flush()
    item = DietItem(diet_id=diet.id, name="Eggs", quantity=2, unit="pcs", sort_order=0)
    db_session.add(item)
    await db_session.flush()

    res = await auth_client.put(
        f"/diets/api/{diet.id}/items/{item.id}",
        json={"name": "Boiled eggs", "quantity": 3, "meal_time": "breakfast"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Boiled eggs"
    assert body["quantity"] == 3
    assert body["meal_time"] == "breakfast"


# ── Scheduler: raw payload TTL cleanup ──


@pytest.mark.asyncio
async def test_raw_response_cleanup_deletes_expired(db_session, test_user):
    from app.training.scheduler import cleanup_expired_raw_responses

    ent = Entity(type="one_time", real_name="E", category="fitness", owner_id=test_user.id)
    db_session.add(ent)
    await db_session.flush()

    expired = ActivityLog(
        user_id=test_user.id,
        entity_id=ent.id,
        status="completed",
        selected_entity_name="E",
        raw_llm_response="secret",
        raw_response_expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    fresh = ActivityLog(
        user_id=test_user.id,
        entity_id=ent.id,
        status="planned",
        selected_entity_name="E",
        raw_llm_response="keep",
        raw_response_expires_at=datetime.now(UTC) + timedelta(days=10),
    )
    db_session.add_all([expired, fresh])
    await db_session.flush()

    deleted = await cleanup_expired_raw_responses(db_session)
    assert deleted == 1
    await db_session.refresh(expired)
    assert expired.raw_llm_response is None
    assert expired.raw_response_expires_at is None
    await db_session.refresh(fresh)
    assert fresh.raw_llm_response == "keep"
