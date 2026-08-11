"""Tests for Points v2, measurements, inventory, schedule, import."""

from datetime import date, time

import pytest

# ── Points v2 engine ──


class TestCalculateEntityPoints:
    async def test_empty_config(self):
        from app.gamification.points_v2 import calculate_entity_points

        net, bonuses, penalties = await calculate_entity_points(None, {})
        assert net == 0
        assert bonuses == []

    async def test_base_points(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {"points": {"base": 15}}
        net, _, _ = await calculate_entity_points(config, {})
        assert net == 15

    async def test_intensity_multiplier(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {"points": {"base": 10}}
        net, _, _ = await calculate_entity_points(config, {"intensity": 3})
        assert net == 12  # 10 * (1 + 2*0.10)

    async def test_bonus_condition_met(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {
            "points": {"base": 10},
            "bonuses": [
                {"code": "extra", "condition": "extra_fluid_ml > 0", "reward": 20, "enabled": True},
            ],
        }
        net, bonuses, _ = await calculate_entity_points(config, {"extra_fluid_ml": 3})
        assert net == 30
        assert len(bonuses) == 1

    async def test_bonus_condition_not_met(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {
            "points": {"base": 10},
            "bonuses": [
                {"code": "extra", "condition": "extra_fluid_ml > 0", "reward": 20},
            ],
        }
        net, bonuses, _ = await calculate_entity_points(config, {})
        assert net == 10
        assert bonuses == []

    async def test_bonus_disabled(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {
            "points": {"base": 10},
            "bonuses": [
                {"code": "x", "condition": "x > 0", "reward": 5, "enabled": False},
            ],
        }
        net, _, _ = await calculate_entity_points(config, {"x": 10})
        assert net == 10

    async def test_multiple_bonuses(self):
        from app.gamification.points_v2 import calculate_entity_points

        config = {
            "points": {"base": 10},
            "bonuses": [
                {"code": "a", "condition": "a > 0", "reward": 5},
                {"code": "b", "condition": "b > 0", "reward": 3},
            ],
        }
        net, bonuses, _ = await calculate_entity_points(config, {"a": 1, "b": 5})
        assert net == 18
        assert len(bonuses) == 2


class TestCalculateEntityPenalty:
    async def test_no_config(self):
        from app.gamification.points_v2 import calculate_entity_penalty

        p = await calculate_entity_penalty(None, "missed")
        assert p == 25

    async def test_disabled_penalties(self):
        from app.gamification.points_v2 import calculate_entity_penalty

        config = {"penalties": {"enabled": False}}
        p = await calculate_entity_penalty(config, "missed")
        assert p == 0

    async def test_missed_penalty(self):
        from app.gamification.points_v2 import calculate_entity_penalty

        config = {
            "penalties": {
                "enabled": True,
                "levels": [
                    {"level": 1, "deduction": 7, "condition": "missed"},
                ],
            }
        }
        p = await calculate_entity_penalty(config, "missed")
        assert p == 7

    async def test_escalation(self):
        from app.gamification.points_v2 import calculate_entity_penalty

        config = {
            "penalties": {
                "enabled": True,
                "escalation": True,
                "escalation_step": 1.5,
                "escalation_cap": 5,
                "levels": [
                    {"level": 1, "deduction": 10, "condition": "missed"},
                ],
            }
        }
        p = await calculate_entity_penalty(config, "missed", escalation_level=3)
        assert p == 20  # 10 * (1 + 2*0.5)

    async def test_escalation_cap(self):
        from app.gamification.points_v2 import calculate_entity_penalty

        config = {
            "penalties": {
                "enabled": True,
                "escalation": True,
                "escalation_step": 1.5,
                "escalation_cap": 3,
                "levels": [
                    {"level": 1, "deduction": 10, "condition": "missed"},
                ],
            }
        }
        p = await calculate_entity_penalty(config, "missed", escalation_level=100)
        assert p == 30  # capped at ×3


class TestConditionEvaluator:
    def test_simple_key_present(self):
        from app.gamification.dsl import eval_condition

        assert eval_condition("x", {"x": 1}) is True
        assert eval_condition("x", {"y": 1}) is False

    def test_numeric_greater(self):
        from app.gamification.dsl import eval_condition

        assert eval_condition("count > 5", {"count": 10}) is True
        assert eval_condition("count > 5", {"count": 3}) is False

    def test_numeric_equals(self):
        from app.gamification.dsl import eval_condition

        assert eval_condition("flag == 1", {"flag": 1}) is True
        assert eval_condition("flag == 1", {"flag": 0}) is False

    def test_string_equals(self):
        from app.gamification.dsl import eval_condition

        assert eval_condition("status == done", {"status": "done"}) is True

    def test_empty_condition(self):
        from app.gamification.dsl import eval_condition

        assert eval_condition("", {}) is False


class TestTypedConditionDsl:
    """REM §5.2 typed gamification DSL — no eval, whitelist validation."""

    def test_valid_bare_field(self):
        from app.gamification.dsl import validate_condition

        assert validate_condition("extra_fluid_ml") is None

    def test_valid_comparison(self):
        from app.gamification.dsl import validate_condition

        assert validate_condition("extra_fluid_ml > 0") is None
        assert validate_condition("count >= 5") is None
        assert validate_condition("flag == true") is None
        assert validate_condition("status == 'done'") is None

    def test_invalid_field_name(self):
        from app.gamification.dsl import validate_condition

        assert validate_condition("1bad_field") is not None
        assert validate_condition("field with spaces") is not None

    def test_unsupported_operator_rejected(self):
        from app.gamification.dsl import validate_condition

        assert validate_condition("x in (1,2)") is not None
        assert validate_condition("x and y") is not None
        assert validate_condition("__import__('os').system('id')") is not None

    def test_invalid_value_rejected(self):
        from app.gamification.dsl import validate_condition

        assert validate_condition("x = os.system('id')") is not None
        assert validate_condition("x > __import__") is not None

    def test_penalty_condition_whitelist(self):
        from app.gamification.dsl import validate_penalty_condition

        assert validate_penalty_condition("missed") is None
        assert validate_penalty_condition("partial") is None
        assert validate_penalty_condition("late") is None
        assert validate_penalty_condition("whenever") is not None

    def test_schema_rejects_bad_bonus_condition(self):
        from pydantic import ValidationError

        from app.schemas.points_v2 import BonusCondition

        BonusCondition(code="b", condition="extra_fluid_ml > 0")
        try:
            BonusCondition(code="b", condition="os.system('id')")
        except ValidationError:
            pass
        else:
            raise AssertionError("dangerous condition string must be rejected")

    def test_schema_rejects_bad_penalty_condition(self):
        from pydantic import ValidationError

        from app.schemas.points_v2 import PenaltyLevel

        PenaltyLevel(level=1, deduction=5, condition="missed")
        try:
            PenaltyLevel(level=1, deduction=5, condition="whenever")
        except ValidationError:
            pass
        else:
            raise AssertionError("unknown failure condition must be rejected")


# ── Schemas ──


class TestGamificationConfigSchema:
    def test_roundtrip(self):
        from app.schemas.points_v2 import (
            BonusCondition,
            GamificationConfig,
            PenaltyConfig,
            PenaltyLevel,
            PointsConfig,
            ThresholdConfig,
        )

        gc = GamificationConfig(
            points=PointsConfig(base=15, max_per_day=100),
            penalties=PenaltyConfig(
                enabled=True,
                levels=[PenaltyLevel(level=1, deduction=5, condition="missed")],
            ),
            bonuses=[BonusCondition(code="x", condition="x > 0", reward=10)],
            thresholds=ThresholdConfig(negative=-100, warning=0, good=100),
        )
        d = gc.model_dump()
        gc2 = GamificationConfig(**d)
        assert gc2.points.base == 15
        assert gc2.penalties.levels[0].deduction == 5


class TestBodyMeasurementSchema:
    def test_create_valid(self):
        from app.schemas.points_v2 import BodyMeasurementCreate

        m = BodyMeasurementCreate(measured_date=date.today(), time_of_day="morning", weight=98.5)
        assert m.weight == 98.5


class TestInventorySchema:
    def test_create_valid(self):
        from app.schemas.points_v2 import InventoryItemCreate

        i = InventoryItemCreate(category="clothing", name="Stockings", quantity=3)
        assert i.category == "clothing"


class TestImportPayload:
    def test_valid(self):
        from app.schemas.points_v2 import ImportPayload

        p = ImportPayload(import_type="measurements", data=[{"weight": 98.5}])
        assert p.import_type == "measurements"


# ── Models ──


@pytest.mark.asyncio
async def test_entity_hierarchy(db_session):
    from app.models.entity import Entity

    parent = Entity(type="one_time", real_name="Parent Task", category="test", level=1)
    db_session.add(parent)
    await db_session.flush()

    child = Entity(type="one_time", real_name="Child Task", category="test", level=10, parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()

    assert child.parent_id == parent.id
    assert child.level == 10


@pytest.mark.asyncio
async def test_entity_gamification_config(db_session, test_user):
    from app.models.entity import Entity

    gc = {"points": {"base": 42}, "penalties": {"enabled": True, "levels": []}}
    entity = Entity(
        type="one_time",
        real_name="Config Test",
        category="test",
        owner_id=test_user.id,
        author_id=test_user.id,
        gamification_config=gc,
    )
    db_session.add(entity)
    await db_session.flush()

    assert entity.gamification_config["points"]["base"] == 42


@pytest.mark.asyncio
async def test_points_transaction(db_session, test_user):
    from app.models.points import PointsTransaction

    txn = PointsTransaction(user_id=test_user.id, amount=50, transaction_type="earn", reason="Test")
    db_session.add(txn)
    await db_session.flush()

    assert txn.amount == 50
    assert txn.transaction_type == "earn"


@pytest.mark.asyncio
async def test_body_measurement(db_session, test_user):
    from app.models.life import BodyMeasurement

    m = BodyMeasurement(
        user_id=test_user.id,
        measured_date=date.today(),
        time_of_day="morning",
        weight=98.5,
        chest=112.0,
    )
    db_session.add(m)
    await db_session.flush()

    assert m.weight == 98.5


@pytest.mark.asyncio
async def test_inventory_item(db_session, test_user):
    from app.models.life import InventoryItem

    item = InventoryItem(
        user_id=test_user.id,
        category="clothing",
        name="Test Item",
        quantity=5,
        is_shopping_list=True,
    )
    db_session.add(item)
    await db_session.flush()

    assert item.is_shopping_list is True
    assert item.quantity == 5


@pytest.mark.asyncio
async def test_schedule_rule(db_session, test_user):
    from app.models.life import ScheduleRule

    rule = ScheduleRule(user_id=test_user.id, day_of_week=0, start_time=time(6, 0), task_type="mandatory")
    db_session.add(rule)
    await db_session.flush()

    assert rule.day_of_week == 0
