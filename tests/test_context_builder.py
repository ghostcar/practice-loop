"""Tests for context builder (unit tests with mocks)."""

import pytest

from app.llm.context_builder import format_context_for_prompt


@pytest.mark.asyncio
async def test_format_context_for_prompt():
    """Context dict is formatted correctly for LLM prompt."""
    context = {
        "stats": {
            "total_activities": 42,
            "completed": 30,
            "stopped": 12,
            "week_activities": 7,
        },
        "allowed_entities": [
            {
                "id": "abc-123",
                "name": "Massage",
                "category": "Care",
                "type": "one_time",
                "desire_level": "want",
                "rating": 4,
                "params_schema": {"duration_minutes": {"min": 10, "max": 20}},
            },
            {
                "id": "def-456",
                "name": "Walk",
                "category": "Romance",
                "type": "one_time",
                "desire_level": "neutral",
                "rating": 3,
                "params_schema": None,
            },
        ],
        "recent_history": [
            {
                "id": "log-1",
                "entity_name": "Massage",
                "status": "completed",
                "params": {"intensity": 3},
                "created_at": "2026-08-07T10:00:00",
            },
        ],
        "active_penalties": [
            {"type": "total_interruptions", "count": 2},
            {"type": "consecutive_interruptions", "count": 1},
        ],
        "locale": "en",
    }

    result = format_context_for_prompt(context)

    assert "## User Stats" in result
    assert "Total activities: 42" in result
    assert "## Allowed Entities" in result
    assert "[want] Massage" in result
    assert "[neutral] Walk" in result
    assert "## Recent History" in result
    assert "[completed] Massage" in result
    assert "## Active Penalties" in result
    assert "total_interruptions: 2" in result
    assert "consecutive_interruptions: 1" in result


@pytest.mark.asyncio
async def test_format_context_empty_penalties():
    """Empty penalties shows 'None'."""
    context = {
        "stats": {
            "total_activities": 0,
            "completed": 0,
            "stopped": 0,
            "week_activities": 0,
        },
        "allowed_entities": [],
        "recent_history": [],
        "active_penalties": [],
        "locale": "en",
    }

    result = format_context_for_prompt(context)
    assert "- None" in result


@pytest.mark.asyncio
async def test_format_context_params_schema():
    """Params schema is included in the prompt."""
    context = {
        "stats": {
            "total_activities": 0,
            "completed": 0,
            "stopped": 0,
            "week_activities": 0,
        },
        "allowed_entities": [
            {
                "id": "abc",
                "name": "Test",
                "category": "Test",
                "type": "one_time",
                "desire_level": "want",
                "rating": 5,
                "params_schema": {"duration": {"min": 5, "max": 15}},
            }
        ],
        "recent_history": [],
        "active_penalties": [],
        "locale": "en",
    }

    result = format_context_for_prompt(context)
    assert "params_schema:" in result
    assert '"duration"' in result
