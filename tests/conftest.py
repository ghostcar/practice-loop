"""Test fixtures: in-memory SQLite, async client, test user factory."""

import asyncio
import os
import secrets
from collections.abc import AsyncGenerator

# Enable LockTimer Core for tests (must be set before app import).
os.environ.setdefault("LOCKTIMER_CORE_ENABLED", "true")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.achievement import Achievement, UserAchievement  # noqa: F401
from app.models.activity_log import ActivityLog  # noqa: F401 — ensure table registry
from app.models.api_token import ApiToken  # noqa: F401
from app.models.body_part import ActivityBodyPartRequirement, BodyPart, TaskBodyTarget  # noqa: F401
from app.models.calendar import AvailabilityWindow, CalendarOverride, CalendarTemplate  # noqa: F401
from app.models.category import ActivityCategory  # noqa: F401
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview  # noqa: F401
from app.models.entity import Entity  # noqa: F401
from app.models.inventory_category import InventoryCategory  # noqa: F401
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule  # noqa: F401
from app.models.llm_config import LLMProviderConfig  # noqa: F401
from app.models.locktimer import (  # noqa: F401
    LockAuditEvent,
    LockInnerPeriod,
    LockJobReceipt,
    LockLlmProposal,
    LockOutboxEvent,
    LockPenaltyEvent,
    LockSession,
    LockSessionSnapshot,
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
    LockTaskRule,
    LockTimerTemplate,
)
from app.models.media import MediaAsset, MediaVerificationResult, VerificationChallenge  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.opt_in import UserEntityOptIn  # noqa: F401
from app.models.points import PenaltyRedemption, PointsProfile, PointsTransaction  # noqa: F401
from app.models.progress import UserProgress  # noqa: F401
from app.models.push_device import PushDevice  # noqa: F401
from app.models.session import ActivitySession  # noqa: F401
from app.models.task_history import ActivityTaskHistory  # noqa: F401
from app.models.task_inventory import ActivityInventoryRequirement, TaskInventoryUsage  # noqa: F401
from app.models.task_location import ActivityLocationRequirement, TaskLocation, TaskLocationUsage  # noqa: F401
from app.models.training import TrainingDay  # noqa: F401
from app.models.user import User
from app.templates_setup import templates

# Disable Jinja2 template caching in tests to avoid unhashable context issues
templates.env.cache = None


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def _engine():
    """Create engine and tables — fresh per test for isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session with fresh tables."""
    test_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_factory() as session:

        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db

        yield session

        await session.rollback()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with DB override."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user and return it."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("secret123"),
        locale="en",
        theme="dark",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    """Cookie + CSRF headers for an authenticated test user."""
    token = create_access_token(test_user.id)
    csrf = secrets.token_hex(32)
    return {
        "Cookie": f"access_token={token}; csrf_token={csrf}",
        "X-CSRF-Token": csrf,
    }


@pytest_asyncio.fixture
async def auth_client(async_client: AsyncClient, auth_headers: dict) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated async client."""
    async_client.headers.update(auth_headers)
    yield async_client
    async_client.headers.pop("Cookie", None)
