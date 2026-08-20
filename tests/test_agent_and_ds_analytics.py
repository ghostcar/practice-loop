"""Integration tests for AI Agent Tool Expansion & D/s Cohort Analytics."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import execute_agent_tool
from app.analytics.engine import (
    compute_multivariable_clusters,
)
from app.models.insights import InsightFinding
from app.models.user import User


def test_multivariable_clusters_computation():
    """Verify compute_multivariable_clusters calculates 3-metric triplets."""
    series_data = {
        "sleep_hours": [7.0, 8.0, 6.0, 7.5, 8.5],
        "wellbeing_score": [3.0, 4.0, 2.0, 4.0, 5.0],
        "workout_minutes": [0.0, 30.0, 0.0, 45.0, 60.0],
        "care_entries": [1.0, 2.0, 0.0, 1.0, 2.0],
    }
    clusters = compute_multivariable_clusters(series_data)
    assert isinstance(clusters, list)
    if clusters:
        assert len(clusters[0]["metrics"]) == 3
        assert "r_score" in clusters[0]


@pytest.mark.asyncio
async def test_agent_create_dynamic_insight_finding_tool(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify AI Agent tool create_dynamic_insight_finding persists InsightFinding in DB."""
    result = await execute_agent_tool(
        db=db_session,
        user_id=test_user.id,
        tool_name="create_dynamic_insight_finding",
        arguments={
            "title": "Интеграционная закономерность",
            "detail": "Сон 8 часов повышает продуктивность на +40%",
            "impact": "positive",
        },
    )
    assert result["status"] == "created"
    assert result["title"] == "Интеграционная закономерность"

    # Verify DB persistence
    finding_res = await db_session.execute(
        select(InsightFinding).where(InsightFinding.title == "Интеграционная закономерность")
    )
    finding = finding_res.scalar_one_or_none()
    assert finding is not None
    assert finding.summary == "Сон 8 часов повышает продуктивность на +40%"


@pytest.mark.asyncio
async def test_agent_get_analytics_correlation_matrix_tool(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify AI Agent tool get_analytics_correlation_matrix returns matrix."""
    result = await execute_agent_tool(
        db=db_session,
        user_id=test_user.id,
        tool_name="get_analytics_correlation_matrix",
        arguments={"days": 14},
    )
    assert result["status"] == "success"
    assert "analytics" in result


@pytest.mark.asyncio
async def test_ds_portal_renders_cohort_analytics(auth_client: AsyncClient):
    """GET /ds/portal renders cohort analytics widget."""
    resp = await auth_client.get("/ds/portal")
    assert resp.status_code == 200
    assert "Обобщенная Аналитика Когорты Ключника" in resp.text
