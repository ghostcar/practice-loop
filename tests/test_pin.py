"""Test real 2FA PIN: set, verify, session cache, change, clear (ADR-152)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPinSetVerify:
    """Basic PIN lifecycle: set → verify → change → clear."""

    async def test_set_pin_success(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        resp = await async_client.post(
            "/security/set-pin",
            data={"pin_code": "123456", "confirm_pin": "123456"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_set_pin_mismatch(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        resp = await async_client.post(
            "/security/set-pin",
            data={"pin_code": "123456", "confirm_pin": "654321"},
        )
        assert resp.status_code == 400

    async def test_set_pin_too_short(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        resp = await async_client.post(
            "/security/set-pin",
            data={"pin_code": "12", "confirm_pin": "12"},
        )
        assert resp.status_code == 400

    async def test_verify_valid_pin(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        # Set PIN first
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "9999", "confirm_pin": "9999"},
        )
        resp = await async_client.post(
            "/security/verify-pin",
            data={"pin_code": "9999"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    async def test_verify_wrong_pin(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "7777", "confirm_pin": "7777"},
        )
        resp = await async_client.post(
            "/security/verify-pin",
            data={"pin_code": "0000"},
        )
        assert resp.status_code == 403

    async def test_verify_before_set(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        resp = await async_client.post(
            "/security/verify-pin",
            data={"pin_code": "1234"},
        )
        assert resp.status_code == 400

    async def test_change_pin_cycle(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        # Set
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "1111", "confirm_pin": "1111"},
        )
        # Change
        resp = await async_client.post(
            "/security/change-pin",
            data={
                "current_pin": "1111",
                "new_pin": "2222",
                "confirm_new_pin": "2222",
            },
        )
        assert resp.status_code == 200
        # Old PIN fails
        resp = await async_client.post("/security/verify-pin", data={"pin_code": "1111"})
        assert resp.status_code == 403
        # New PIN works
        resp = await async_client.post("/security/verify-pin", data={"pin_code": "2222"})
        assert resp.status_code == 200

    async def test_clear_pin_cycle(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "3333", "confirm_pin": "3333"},
        )
        resp = await async_client.post("/security/clear-pin", data={"current_pin": "3333"})
        assert resp.status_code == 200
        # After clear, verify should fail
        resp = await async_client.post("/security/verify-pin", data={"pin_code": "3333"})
        assert resp.status_code == 400

    async def test_pin_status_flow(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        # No PIN
        resp = await async_client.get("/security/pin-status")
        data = resp.json()
        assert data["has_pin"] is False
        # Set PIN
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "5555", "confirm_pin": "5555"},
        )
        resp = await async_client.get("/security/pin-status")
        data = resp.json()
        assert data["has_pin"] is True

    async def test_double_set_rejected(self, auth_headers: dict, async_client: AsyncClient):
        async_client.headers.update(auth_headers)
        await async_client.post(
            "/security/set-pin",
            data={"pin_code": "8888", "confirm_pin": "8888"},
        )
        resp = await async_client.post(
            "/security/set-pin",
            data={"pin_code": "8888", "confirm_pin": "8888"},
        )
        assert resp.status_code == 400  # PIN already set
