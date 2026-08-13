"""Import handlers — points transactions & points profiles."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.points import PointsProfile, PointsTransaction
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_points_transactions(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            entity_id = None
            entity_name = row.get("entity_name") or row.get("entity_code")
            if entity_name:
                e_result = await db.execute(
                    select(Entity.id)
                    .where(
                        Entity.real_name == str(entity_name),
                        (Entity.owner_id == user.id) | Entity.is_public.is_(True),
                    )
                    .limit(1)
                )
                e_row = e_result.first()
                if e_row:
                    entity_id = e_row[0]

            created_at = datetime.now(UTC)
            if row.get("created_at"):
                created_at = datetime.fromisoformat(str(row["created_at"]))

            txn = PointsTransaction(
                user_id=user.id,
                amount=int(row.get("amount", 0)),
                transaction_type=str(row.get("transaction_type", "earn")),
                reason=str(row.get("reason", "")) or None,
                entity_id=entity_id,
                created_at=created_at,
            )
            db.add(txn)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip points_transaction row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}


async def _import_points_profiles(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            config = row.get("config", {})
            if isinstance(config, str) and config:
                config = json.loads(config)

            profile = PointsProfile(
                user_id=user.id,
                name=str(row.get("name", "Unnamed Profile")),
                config=config,
                is_default=str(row.get("is_default", "false")).lower() == "true",
            )
            db.add(profile)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip points_profile row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}
