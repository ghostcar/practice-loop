"""Gate A остаток — аудит PROJECT_REVIEW_2026-08-13 (Session 119).

P1-1 — LockTimer validate больше не использует innerHTML (textContent-based DOM).
P2-3 — /healthz/readiness не раскрывает текст исключения клиенту.
P1-6 — базовые security headers (HSTS/nosniff/Referrer/X-Frame-Options/Permissions-Policy) + CSP report-only.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.services.execution import add_slot_rule, create_draft
from app.models.user import User

pytestmark = pytest.mark.anyio

XSS_PAYLOAD = '<script>alert("xss")</script><img src=x onerror=alert(1)>'


# ---------------------------------------------------------------------------
# P1-1 — LockTimer validate: XSS regression
# ---------------------------------------------------------------------------


def test_session_detail_template_has_no_inner_html() -> None:
    """Audit P1-1: the validate banner must be built via textContent, not innerHTML.

    A user-controlled rule name reaching warnings/errors would otherwise turn
    into stored/reflected XSS. The template is the security boundary here.
    """
    path = pathlib.Path("app/templates/locktimer/session_detail.html")
    src = path.read_text(encoding="utf-8")
    assert "innerHTML" not in src, "innerHTML is forbidden in session_detail.html (audit P1-1)"


async def test_validate_returns_payload_as_data_not_html(
    db_session: AsyncSession,
    auth_client,
    test_user: User,
) -> None:
    """The validate endpoint returns warnings/errors as plain JSON strings.

    A malicious rule name must round-trip as a string (safe for textContent),
    never be rendered as HTML server-side.
    """
    session = await create_draft(db_session, owner_id=test_user.id, timezone_str="UTC")
    await add_slot_rule(
        db_session,
        session_id=session.id,
        name=f"Morning slot {XSS_PAYLOAD}",
        rule_type=e.SLOT_RULE_EVERY_N_DAYS,
        schedule={"n": 1, "time_of_day": "09:00", "start_date": "2026-08-01T00:00:00+00:00"},
        duration_seconds=1800,
    )

    response = await auth_client.post(f"/api/v2/locktimer/sessions/{session.id}/validate")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "errors" in data and isinstance(data["errors"], list)
    for item in data["errors"] + data["warnings"]:
        assert isinstance(item, str)
        # Data is a plain string — the client must use textContent; no server-side
        # HTML embedding should exist (Jinja autoescape would be fine, but the
        # validate response is JSON consumed via fetch).
        assert "<script>" not in item


# ---------------------------------------------------------------------------
# P2-3 — readiness never leaks exception details
# ---------------------------------------------------------------------------


async def test_readiness_hides_exception_details(async_client, monkeypatch) -> None:
    """Audit P2-3: on DB failure the client gets a bare 'not ready', 503.

    Exception internals (hostname, DB name, connection details) must go to the
    server log only.
    """
    from app.database import get_db
    from app.main import app

    async def broken_get_db():
        raise RuntimeError("secret db host: db.internal:5432/user=admin")

    app.dependency_overrides[get_db] = broken_get_db
    try:
        response = await async_client.get("/healthz/readiness")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.text.strip() == "not ready"
    assert "secret db host" not in response.text
    assert "db.internal" not in response.text
    assert "admin" not in response.text


# ---------------------------------------------------------------------------
# P1-6 — baseline security headers
# ---------------------------------------------------------------------------


async def test_security_headers_present_on_html_pages(async_client) -> None:
    """Audit P1-6: every response carries the baseline security headers."""
    response = await async_client.get("/login")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers.get("permissions-policy", "")
    assert "content-security-policy-report-only" in response.headers


async def test_security_headers_on_api_response(async_client) -> None:
    """Headers apply to API responses too, not just pages."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "content-security-policy-report-only" in response.headers
    # HSTS only on https (test client is http).
    assert "strict-transport-security" not in response.headers


async def test_hsts_only_on_https(async_client) -> None:
    """HSTS must only be sent on https requests."""
    # Direct unit-style call through the middleware with a forced https scheme
    # (httpx test client is plain http, so the header must not appear there).

    class FakeRequest:
        url = type("URL", (), {"scheme": "https"})()  # type: ignore[attr-defined]

        async def _body(self):  # pragma: no cover - unused
            return b""

    async def fake_call_next(request):  # noqa: ARG001
        from starlette.responses import Response

        return Response("ok")

    from app.main import security_headers_middleware

    response = await security_headers_middleware(FakeRequest(), fake_call_next)  # type: ignore[arg-type]
    assert response.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
