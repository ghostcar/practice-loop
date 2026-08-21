"""Test fixtures: in-memory SQLite, async client, test user factory."""

import os
import secrets
from collections.abc import AsyncGenerator

# Enable LockTimer Core for tests (must be set before app import).
os.environ.setdefault("LOCKTIMER_CORE_ENABLED", "true")
os.environ.setdefault("KB_CONTEXT_ENABLED", "false")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.achievement import Achievement, UserAchievement  # noqa: F401
from app.models.activity_log import ActivityLog  # noqa: F401 — ensure table registry
from app.models.aftercare import AftercareEntry  # noqa: F401
from app.models.api_token import ApiToken  # noqa: F401
from app.models.body_part import ActivityBodyPartRequirement, BodyPart, TaskBodyTarget  # noqa: F401
from app.models.calendar import AvailabilityWindow, CalendarOverride, CalendarTemplate  # noqa: F401
from app.models.care import (  # noqa: F401
    CareCourse,
    CareCourseSession,
    CareEntry,
    CareEntryProduct,
    CareProduct,
    CareRoutine,
    CareRoutineProduct,
)
from app.models.catalog import ActivityCatalogItem  # noqa: F401
from app.models.category import ActivityCategory  # noqa: F401
from app.models.chastity import ChastityCheckIn  # noqa: F401
from app.models.consent import ConsentRecord  # noqa: F401
from app.models.device import ChastityDeviceEvent  # noqa: F401
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview  # noqa: F401
from app.models.entity import Entity  # noqa: F401
from app.models.health import CycleEvent, CycleSettings, HealthState, LabRecord  # noqa: F401
from app.models.insights import InsightFinding, InsightRun  # noqa: F401
from app.models.inventory_category import InventoryCategory  # noqa: F401
from app.models.journal import JournalEntry, JournalPartner  # noqa: F401
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
from app.models.medication import Medication, MedIntake, MedKit, MedSchedule, MedStock  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.opt_in import UserEntityOptIn  # noqa: F401
from app.models.points import PenaltyRedemption, PointsProfile, PointsTransaction  # noqa: F401
from app.models.progress import UserProgress  # noqa: F401
from app.models.push_device import PushDevice  # noqa: F401
from app.models.reminder_log import ReminderLog  # noqa: F401
from app.models.session import ActivitySession  # noqa: F401
from app.models.session_history import ActivitySessionHistory  # noqa: F401
from app.models.task_history import ActivityTaskHistory  # noqa: F401
from app.models.task_inventory import ActivityInventoryRequirement, TaskInventoryUsage  # noqa: F401
from app.models.task_location import ActivityLocationRequirement, TaskLocation, TaskLocationUsage  # noqa: F401
from app.models.training import TrainingDay  # noqa: F401
from app.models.user import User
from app.templates_setup import templates

# Disable Jinja2 template caching in tests to avoid unhashable context issues
templates.env.cache = None


@pytest.fixture(scope="session")
def _database_path(tmp_path_factory) -> str:
    """Create the complete SQLite schema once, independently of event loops."""
    database_path = tmp_path_factory.mktemp("practiceloop-db") / "tests.sqlite3"
    sync_engine = create_engine(f"sqlite:///{database_path}")
    try:
        Base.metadata.create_all(sync_engine)
    finally:
        sync_engine.dispose()
    return str(database_path)


@pytest_asyncio.fixture(scope="function")
async def _engine(_database_path: str):
    """Open a lightweight async engine over the session-scoped schema.

    Rebuilding the complete metadata for every test dominated the suite runtime
    (more than 1,200 full create_all passes).  The connection-level transaction
    in ``db_session`` is rolled back after each test, including application code
    that calls ``Session.commit()``.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{_database_path}", echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated session without rebuilding the schema."""
    async with _engine.connect() as connection:
        # SQLite defers BEGIN until the first write.  A Session savepoint could
        # otherwise become the outermost transaction and Session.commit()
        # would persist data into the shared test database.  Materialize the
        # outer transaction before creating any savepoint.
        await connection.exec_driver_sql("BEGIN")
        test_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async with test_factory() as session:

            async def override_get_db():
                yield session

            app.dependency_overrides[get_db] = override_get_db

            try:
                yield session
            finally:
                app.dependency_overrides.clear()
                await session.close()

        await connection.rollback()


@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with DB override."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, _test_password_hash: str) -> User:
    """Create a test user and return it."""
    user = User(
        email="test@example.com",
        password_hash=_test_password_hash,
        locale="en",
        theme="dark",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession, _test_password_hash: str) -> User:
    """Second test user for membership / multi-user flows."""
    user = User(
        email="second@example.com",
        password_hash=_test_password_hash,
        locale="en",
        theme="dark",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture(scope="session")
def _test_password_hash() -> str:
    """Hash the shared fixture password once; password tests use real calls."""
    return hash_password("secret123")


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
