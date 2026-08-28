"""Tests for optional TOTP 2FA (ADR-152 extension)."""

import pyotp
import pytest
from httpx import AsyncClient

from app.encryption import decrypt_api_key


@pytest.mark.asyncio
class TestTotpLifecycle:
    async def test_setup_returns_uri_without_secret(self, auth_client: AsyncClient, test_user):
        response = await auth_client.post("/security/totp/setup")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"
        assert payload["provisioning_uri"].startswith("otpauth://totp/")
        assert "secret=" not in payload["provisioning_uri"].lower() or "issuer=" in payload["provisioning_uri"]
        assert test_user.totp_secret_encrypted
        assert test_user.totp_secret_encrypted != decrypt_api_key(test_user.totp_secret_encrypted)
        assert test_user.totp_enabled is False

    async def test_confirm_enable_verify_and_disable(self, auth_client: AsyncClient, test_user):
        await auth_client.post("/security/totp/setup")
        secret = decrypt_api_key(test_user.totp_secret_encrypted)
        code = pyotp.TOTP(secret).now()

        response = await auth_client.post("/security/totp/confirm", data={"code": code})
        assert response.status_code == 200
        assert response.json()["status"] == "enabled"

        response = await auth_client.post("/security/totp/verify", data={"code": pyotp.TOTP(secret).now()})
        assert response.status_code == 200
        assert response.json()["method"] == "totp"

        response = await auth_client.post("/security/totp/disable", data={"code": pyotp.TOTP(secret).now()})
        assert response.status_code == 200
        assert response.json()["status"] == "disabled"

    async def test_invalid_code_does_not_enable(self, auth_client: AsyncClient, test_user):
        await auth_client.post("/security/totp/setup")
        response = await auth_client.post("/security/totp/confirm", data={"code": "000000"})
        assert response.status_code == 403
        assert test_user.totp_enabled is False

    async def test_status_does_not_expose_secret(self, auth_client: AsyncClient):
        response = await auth_client.get("/security/totp-status")
        assert response.status_code == 200
        assert response.json() == {"enabled": False}
