import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_agency_api_endpoints(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    # 1. GET /agency UI
    res = await async_client.get("/agency", headers=auth_headers)
    assert res.status_code == 200
    assert "Agency Policy" in res.text

    # 2. POST /agency/sessions HTML form
    post_res = await async_client.post(
        "/agency/sessions",
        data={
            "default_level": "assisted",
            "constraints_json": '{"max_duration_min": 45}',
        },
        headers=auth_headers,
        follow_redirects=False,
    )
    assert post_res.status_code == 303

    # 3. GET /api/v2/agency JSON
    json_res = await async_client.get("/api/v2/agency", headers=auth_headers)
    assert json_res.status_code == 200
    data = json_res.json()
    assert "policies" in data
    session_p = next(p for p in data["policies"] if p["domain"] == "sessions")
    assert session_p["default_level"] == "assisted"
    assert session_p["constraints"]["max_duration_min"] == 45
