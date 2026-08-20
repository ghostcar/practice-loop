"""Integration tests for 6 Advanced Platform Enhancements."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.pdf_reports import generate_monthly_user_report
from app.agent.stress_test import evaluate_pre_session_readiness
from app.models.promocodes import PromoCode
from app.models.user import User
from app.telegram.broadcast import send_telegram_direct_notification


@pytest.mark.asyncio
async def test_telegram_direct_message_broadcast(db_session: AsyncSession, test_user: User):
    """Verify sending direct notifications via Telegram bot."""
    res = await send_telegram_direct_notification(db_session, test_user.id, message_text="ALERT: Session starting")
    assert res["status"] == "delivered"
    assert res["email"] == test_user.email


@pytest.mark.asyncio
async def test_claim_promocode_upgrades_user_subscription(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    """Verify claiming promotional code upgrades subscription tier."""
    promo = PromoCode(code="GIFT30D", tier_grant="VIP", duration_days=30, max_claims=10)
    db_session.add(promo)
    await db_session.commit()

    resp = await auth_client.post("/billing/promocodes/claim", data={"code": "GIFT30D"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["granted_tier"] == "VIP"


@pytest.mark.asyncio
async def test_generate_monthly_user_report(db_session: AsyncSession, test_user: User):
    """Verify generating monthly visual progress report."""
    rep = await generate_monthly_user_report(db_session, test_user)
    assert rep["status"] == "success"
    assert "Ежемесячный Отчет Практик" in rep["report_title"]


def test_evaluate_pre_session_readiness():
    """Verify pre-session readiness score calculation."""
    res_good = evaluate_pre_session_readiness([5, 4, 5, 4, 5])
    assert res_good["status"] == "success"
    assert res_good["readiness_score"] >= 80.0
    assert res_good["is_load_restricted"] is False

    res_low = evaluate_pre_session_readiness([1, 1, 1, 1, 1])
    assert res_low["readiness_score"] <= 30.0
    assert res_low["is_load_restricted"] is True


@pytest.mark.asyncio
async def test_public_certificate_verification_page(auth_client: AsyncClient):
    """GET /certificates/{cert_id}/verify renders certificate page."""
    resp = await auth_client.get("/certificates/CERT-12345/verify")
    assert resp.status_code == 200
    assert "Сертификат Завершения Программы" in resp.text


@pytest.mark.asyncio
async def test_security_2fa_pin_verification(auth_client: AsyncClient, test_user: User):
    """POST /security/verify-pin verifies 2FA PIN code."""
    resp = await auth_client.post("/security/verify-pin", data={"pin_code": "1234"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"
