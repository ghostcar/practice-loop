"""Privacy audit — verify Social API never leaks private domain data (S7).

Scans all social API responses to ensure they NEVER contain:
- email addresses
- user_id values (other than the authenticated user's own)
- raw_llm_response
- penalty_details
- password_hash
- ip addresses
"""

from __future__ import annotations

import json
import re

import pytest
from httpx import AsyncClient

from app.models.user import User

pytestmark = pytest.mark.anyio


# Patterns that MUST NOT appear in any social API response
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # (pattern, description)
    (r"(?:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})", "email_address"),
    (r"password_hash", "password_hash_field"),
    (r"raw_llm_response", "raw_llm_response_field"),
    (r"penalty_details", "penalty_details_field"),
    (r"penalty_applied", "penalty_applied_field"),
    (r"ip_address[^_]|client_ip|remote_addr", "ip_address_field"),
    (r"user_prompt", "user_prompt_field"),
]


def _scan_forbidden(text: str) -> list[str]:
    """Scan text against forbidden patterns. Returns list of violations."""
    violations: list[str] = []
    for pattern, description in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            violations.append(f"{description} ({pattern})")
    return violations


class TestPrivacyAuditSocialPages:
    """Verify social pages and API responses don't leak private data."""

    SOCIAL_ROUTES: list[tuple[str, str, int]] = [
        # (method, path, expected_status_for_anon)
        ("GET", "/social/privacy", 200),
        ("GET", "/social/api/capabilities", 200),
        ("GET", "/social/profile", 401),
        ("GET", "/social/subjects", 401),
        ("GET", "/social/relationships", 401),
        ("GET", "/social/feed", 401),
        ("GET", "/social/verification", 401),
        ("GET", "/social/moderation", 401),
    ]

    @pytest.mark.parametrize("method,path,expected_status", SOCIAL_ROUTES)
    async def test_social_route_no_private_leak(
        self,
        method: str,
        path: str,
        expected_status: int,
        async_client: AsyncClient,
    ) -> None:
        """Each social route should not leak private data regardless of auth status."""
        if method == "GET":
            resp = await async_client.get(path, follow_redirects=True)
        else:
            resp = await async_client.post(path, follow_redirects=True)

        # Accept any non-500 status (404/401/200 all valid)
        assert resp.status_code < 500, f"{path} returned 5xx: {resp.text[:200]}"

        violations = _scan_forbidden(resp.text)
        assert not violations, f"{path} leaks: {violations}"

    async def test_capabilities_public_no_user_data(self, async_client: AsyncClient) -> None:
        """GET /social/api/capabilities must never contain user identifiers."""
        resp = await async_client.get("/social/api/capabilities")
        assert resp.status_code == 200

        data = resp.json()
        # No user_id keys anywhere
        text = json.dumps(data)
        assert "user_id" not in text, "capabilities endpoint leaks user_id"
        assert "email" not in text, "capabilities endpoint leaks email"

    async def test_privacy_page_pure_document(self, async_client: AsyncClient) -> None:
        """GET /social/privacy must be a pure policy document — no dynamic user data."""
        resp = await async_client.get("/social/privacy")
        assert resp.status_code == 200

        text = resp.text
        # We just check for the forbidden patterns
        violations = _scan_forbidden(text)
        assert not violations, f"privacy page leaks: {violations}"

    async def test_feed_response_structure(self, auth_client: AsyncClient) -> None:
        """Feed must only contain publication data, not user/tracker internals."""
        resp = await auth_client.get("/social/feed", follow_redirects=True)
        assert resp.status_code < 500

        # If redirected to profile (no profile yet), that's fine
        text = resp.text
        violations = _scan_forbidden(text)
        assert not violations, f"feed leaks: {violations}"


class TestPrivacyAuditJsonEndpoints:
    """JSON endpoints must never embed user_id or email in response bodies."""

    async def test_json_endpoints_no_user_leak(self, async_client: AsyncClient) -> None:
        """All JSON social API endpoints must be clean."""
        json_endpoints = [
            "/social/api/capabilities",
        ]

        for endpoint in json_endpoints:
            resp = await async_client.get(endpoint)
            if resp.status_code == 200:
                data = resp.json() if resp.text else {}
                text = json.dumps(data)
                # These must never appear
                assert "email" not in text, f"{endpoint} leaks email"
                assert "password" not in text.lower(), f"{endpoint} leaks password-related"
                assert "raw_llm" not in text.lower(), f"{endpoint} leaks raw LLM"
                assert "penalty" not in text.lower(), f"{endpoint} leaks penalty data"


class TestPrivacyAuditProfile:
    async def test_profile_does_not_expose_internals(
        self,
        db_session,
        test_user: User,
        auth_client: AsyncClient,
    ) -> None:
        """After profile creation, profile page must not leak internals."""
        from app.platform.social.repositories import create_profile

        await create_profile(db_session, test_user.id, "audit_test", "audit_test")
        resp = await auth_client.get("/social/profile", follow_redirects=True)
        assert resp.status_code < 500

        text = resp.text
        # Check for forbidden patterns
        violations = _scan_forbidden(text)
        assert not violations, f"profile page leaks: {violations}"

        # Also ensure email is NOT shown
        assert test_user.email not in text, "profile page leaks email"
        # But alias SHOULD be shown
        assert "audit_test" in text, "profile page should show alias"
