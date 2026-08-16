import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import settings
from app.models import Base  # noqa: F401 — import all models for autogenerate
from app.models.achievement import Achievement, UserAchievement  # noqa: F401
from app.models.activity_log import ActivityLog  # noqa: F401
from app.models.api_token import ApiToken  # noqa: F401
from app.models.body_part import ActivityBodyPartRequirement, BodyPart, TaskBodyTarget  # noqa: F401
from app.models.category import ActivityCategory  # noqa: F401
from app.models.entity import Entity  # noqa: F401
from app.models.inventory_category import InventoryCategory  # noqa: F401
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule  # noqa: F401
from app.models.llm_config import LLMProviderConfig  # noqa: F401
from app.models.locktimer import (  # noqa: F401
    LockAuditEvent,
    LockInnerPeriod,
    LockJobReceipt,
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
from app.models.media import MediaAsset, MediaVerificationResult  # noqa: F401
from app.models.medication import Medication, MedIntake, MedKit, MedSchedule, MedStock  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.opt_in import UserEntityOptIn  # noqa: F401
from app.models.progress import UserProgress  # noqa: F401
from app.models.prompt_template import PromptTemplate  # noqa: F401
from app.models.push_device import PushDevice  # noqa: F401
from app.models.session import ActivitySession  # noqa: F401
from app.models.task_history import ActivityTaskHistory  # noqa: F401
from app.models.task_inventory import ActivityInventoryRequirement, TaskInventoryUsage  # noqa: F401
from app.models.task_location import ActivityLocationRequirement, TaskLocation, TaskLocationUsage  # noqa: F401
from app.models.training import TrainingDay  # noqa: F401
from app.models.user import User  # noqa: F401
from app.platform.social.models import (  # noqa: F401
    ModerationAction,
    ModerationReport,
    SocialBlock,
    SocialComment,
    SocialConsent,
    SocialEncouragement,
    SocialGrant,
    SocialNotification,
    SocialProfile,
    SocialPublication,
    SocialRelationship,
    SocialSubject,
    SocialVerificationPolicy,
    SocialVerificationRequest,
    SocialVerificationVote,
)

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
