"""Clean browser page route regression tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "page, legacy",
    [
        ("/body-parts", "/api/v2/body-parts/page"),
        ("/measurements", "/api/v2/measurements/page"),
        ("/inventory", "/api/v2/inventory/page"),
        ("/schedule", "/api/v2/schedule/page"),
        ("/points", "/api/v2/points/page"),
    ],
)
async def test_clean_page_routes_render(auth_client, page, legacy):
    response = await auth_client.get(page)
    assert response.status_code == 200, page
    assert "<html" in response.text
    legacy_response = await auth_client.get(legacy)
    assert legacy_response.status_code != 200, legacy


async def test_sidebar_uses_clean_page_links(auth_client):
    response = await auth_client.get("/dashboard")
    assert response.status_code == 200
    for path in ("/body-parts", "/measurements", "/inventory", "/schedule", "/points"):
        assert f'href="{path}"' in response.text
