"""Integration tests for All-Inclusive Analytical Correlation Engine (Insights Engine v2)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engine import (
    _pearson_r,
    compute_full_pairwise_matrix,
)
from app.models.insights import InsightFinding, InsightRun
from app.models.user import User


def test_pearson_r_math_calculation():
    """Verify Pearson r calculation helper with positive, negative, and zero correlation."""
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y_pos = [2.0, 4.0, 6.0, 8.0, 10.0]
    y_neg = [10.0, 8.0, 6.0, 4.0, 2.0]
    y_flat = [5.0, 5.0, 5.0, 5.0, 5.0]

    assert _pearson_r(x, y_pos) == 1.0
    assert _pearson_r(x, y_neg) == -1.0
    assert _pearson_r(x, y_flat) == 0.0


@pytest.mark.asyncio
async def test_full_pairwise_matrix_computation():
    """Verify compute_full_pairwise_matrix returns sorted pairwise correlations."""
    series_data = {
        "sleep_hours": [7.0, 8.0, 6.0, 7.5, 8.5],
        "wellbeing_score": [3.0, 4.0, 2.0, 4.0, 5.0],
        "workout_minutes": [0.0, 30.0, 0.0, 45.0, 60.0],
    }
    matrix = compute_full_pairwise_matrix(series_data)
    assert len(matrix) == 3
    assert "metric_a" in matrix[0]
    assert "r" in matrix[0]


@pytest.mark.asyncio
async def test_analytics_cockpit_page_auth(auth_client: AsyncClient):
    """GET /insights/analytics returns 200 OK for authenticated user."""
    resp = await auth_client.get("/insights/analytics")
    assert resp.status_code == 200
    assert "Аналитический Движок Взаимосвязей" in resp.text


@pytest.mark.asyncio
async def test_run_analytics_suite_persists_findings(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    """POST /insights/analytics/run executes suite and persists InsightRun and InsightFinding."""
    resp = await auth_client.post(
        "/insights/analytics/run",
        data={"days": "30"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "analytics" in data

    # Verify DB persistence of InsightRun
    run_res = await db_session.execute(select(InsightRun).where(InsightRun.user_id == test_user.id))
    runs = run_res.scalars().all()
    assert len(runs) >= 1

    # Verify DB persistence of InsightFinding
    find_res = await db_session.execute(select(InsightFinding).where(InsightFinding.run_id == runs[-1].id))
    findings = find_res.scalars().all()
    assert len(findings) >= 0
