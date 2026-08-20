"""Tests for Platform Social Gamification Hub (Steps 88-90)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import UserProgress
from app.models.user import User
from app.platform.social.models import SocialEncouragement, SocialProfile, SocialPublication, SocialSubject


@pytest.mark.asyncio
async def test_social_pillory_board(auth_client: AsyncClient):
    """GET /social/pillory — Community Pillory Board."""
    response = await auth_client.get("/social/pillory")
    assert response.status_code == 200
    assert "Позорный Столб" in response.text


@pytest.mark.asyncio
async def test_social_verification_board(auth_client: AsyncClient):
    """Users without an explicit social profile are sent to opt in first."""
    response = await auth_client.get("/social/verification")
    assert response.status_code == 303
    assert response.headers["location"] == "/social/profile"


@pytest.mark.asyncio
async def test_social_leaderboard(auth_client: AsyncClient):
    """GET /social/leaderboard — Anonymized Community Leaderboard."""
    response = await auth_client.get("/social/leaderboard")
    assert response.status_code == 200
    assert "Лидерборд" in response.text


@pytest.mark.asyncio
async def test_social_kudos_reaction_is_persisted_and_idempotent(
    auth_client: AsyncClient, db_session: AsyncSession, _test_password_hash: str
):
    """A peer receives XP only for the first durable kudos."""
    peer = User(email="peer@example.com", password_hash=_test_password_hash)
    db_session.add(peer)
    await db_session.flush()
    profile = SocialProfile(user_id=peer.id, alias="peer_test", alias_normalized="peer_test", discoverable=True)
    db_session.add(profile)
    await db_session.flush()

    payload = {
        "target_alias": "peer_test",
        "reaction": "fire",
    }
    response = await auth_client.post(
        "/social/kudos",
        data=payload,
        follow_redirects=False,
    )
    repeated = await auth_client.post("/social/kudos", data=payload, follow_redirects=False)

    assert response.status_code == repeated.status_code == 303
    encouragement_count = await db_session.scalar(
        select(func.count()).select_from(SocialEncouragement).where(SocialEncouragement.target_id == profile.id)
    )
    progress = await db_session.get(UserProgress, peer.id)
    assert encouragement_count == 1
    assert progress is not None and progress.xp == 10


@pytest.mark.asyncio
async def test_pillory_uses_publication_and_vote_is_idempotent(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User, _test_password_hash: str
):
    owner = User(email="publisher@example.com", password_hash=_test_password_hash)
    db_session.add(owner)
    await db_session.flush()
    subject = SocialSubject(owner_id=owner.id, subject_type="tracker.pillory", domain_object_id="opaque-1")
    db_session.add(subject)
    await db_session.flush()
    publication = SocialPublication(
        owner_id=owner.id,
        subject_id=subject.id,
        visibility="public",
        snapshot={"title": "Consent publication", "summary": "Redacted"},
        snapshot_hash="a" * 64,
        subject_namespace="tracker.pillory",
    )
    db_session.add(publication)
    await db_session.flush()

    page = await auth_client.get("/social/pillory")
    assert page.status_code == 200
    assert "Consent publication" in page.text

    payload = {"publication_id": str(publication.id), "vote_type": "add_15m"}
    first = await auth_client.post("/social/pillory/vote", data=payload, follow_redirects=False)
    repeated = await auth_client.post("/social/pillory/vote", data=payload, follow_redirects=False)
    assert first.status_code == repeated.status_code == 303
    votes = await db_session.scalar(
        select(func.count()).select_from(SocialEncouragement).where(SocialEncouragement.target_id == publication.id)
    )
    progress = await db_session.get(UserProgress, test_user.id)
    assert votes == 1
    assert progress is not None and progress.xp == 15
