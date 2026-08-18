"""S3 PostgreSQL verification for durable consent serialization.

Requires DATABASE_URL pointing at a disposable database migrated to head.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.consent import record_consent, require_consent
from app.models.aftercare import AftercareEntry
from app.models.category import ActivityCategory  # noqa: F401 — resolve Entity relationship mapper
from app.models.chastity import ChastityCheckIn
from app.models.consent import ConsentRecord
from app.models.device import ChastityDeviceEvent
from app.models.entity import Entity  # noqa: F401 — resolve opt-in relationship mapper
from app.models.journal import JournalEntry  # noqa: F401 — referenced table metadata
from app.models.life import InventoryItem  # noqa: F401 — referenced table metadata
from app.models.locktimer import LockSession  # noqa: F401 — referenced table metadata
from app.models.media import MediaAsset, MediaVerificationResult  # noqa: F401 — referenced table metadata
from app.models.opt_in import UserEntityOptIn  # noqa: F401 — resolve User relationship mapper
from app.models.user import User


async def _write_state(factory: async_sessionmaker, user_id: uuid.UUID, state: str) -> uuid.UUID:
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        row = await record_consent(db, user, "media_verification", state, scope="s3_postgres")
        await db.commit()
        return row.id


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        user = User(email=f"s3-consent-{uuid.uuid4()}@example.invalid", password_hash="not-used")
        db.add(user)
        await db.commit()
        user_id = user.id

    first_ids = await asyncio.gather(
        _write_state(factory, user_id, "granted"),
        _write_state(factory, user_id, "granted"),
    )
    assert first_ids[0] == first_ids[1], "concurrent identical grant must be idempotent"

    async with factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(ConsentRecord)
            .where(ConsentRecord.user_id == user_id, ConsentRecord.consent_type == "media_verification")
        )
        assert count == 1

    await _write_state(factory, user_id, "revoked")
    async with factory() as db:
        try:
            await require_consent(db, user_id, "media_verification")
        except HTTPException as exc:
            assert exc.status_code == 428
        else:  # pragma: no cover - verification script guard
            raise AssertionError("revoked consent must block the protected operation")

    second_ids = await asyncio.gather(
        _write_state(factory, user_id, "granted"),
        _write_state(factory, user_id, "granted"),
    )
    assert second_ids[0] == second_ids[1], "concurrent re-grant must be idempotent"

    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(ConsentRecord)
                    .where(ConsentRecord.user_id == user_id, ConsentRecord.consent_type == "media_verification")
                    .order_by(ConsentRecord.version)
                )
            )
            .scalars()
            .all()
        )
        assert [(row.version, row.state, row.terms_version) for row in rows] == [
            (1, "granted", "1"),
            (2, "revoked", "1"),
            (3, "granted", "1"),
        ]
        db.add_all(
            [
                ChastityDeviceEvent(user_id=user_id, event_type="comfort", comfort_level=4),
                ChastityCheckIn(user_id=user_id, mood=4, comfort_level=5),
                AftercareEntry(user_id=user_id, entry_date=date.today(), kind="rest", comfort_level=4),
            ]
        )
        await db.flush()
        assert (
            await db.scalar(
                select(func.count()).select_from(ChastityDeviceEvent).where(ChastityDeviceEvent.user_id == user_id)
            )
            == 1
        )
        assert (
            await db.scalar(select(func.count()).select_from(ChastityCheckIn).where(ChastityCheckIn.user_id == user_id))
            == 1
        )
        assert (
            await db.scalar(select(func.count()).select_from(AftercareEntry).where(AftercareEntry.user_id == user_id))
            == 1
        )
        user = await db.get(User, user_id)
        assert user is not None
        await db.delete(user)
        await db.commit()

    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(ChastityDeviceEvent).where(ChastityDeviceEvent.user_id == user_id)
            )
            == 0
        )
        assert (
            await db.scalar(select(func.count()).select_from(ChastityCheckIn).where(ChastityCheckIn.user_id == user_id))
            == 0
        )
        assert (
            await db.scalar(select(func.count()).select_from(AftercareEntry).where(AftercareEntry.user_id == user_id))
            == 0
        )

    await engine.dispose()
    print("S3_CONSENT_POSTGRES_OK")


if __name__ == "__main__":
    asyncio.run(main())
