"""LockTimer outbox + job runner — domain events and lease-based job queue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locktimer import LockJobReceipt, LockOutboxEvent


def _now() -> datetime:
    return datetime.now(UTC)


async def emit_outbox_event(
    db: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict | None = None,
    available_at: datetime | None = None,
) -> LockOutboxEvent:
    """Write a domain event to the outbox (same transaction)."""
    event = LockOutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload or {},
        state="pending",
        attempts=0,
        available_at=available_at or _now(),
    )
    db.add(event)
    await db.flush()
    return event


async def enqueue_job(
    db: AsyncSession,
    *,
    job_key: str,
    job_type: str,
    payload: dict | None = None,
    run_after: datetime | None = None,
) -> LockJobReceipt:
    """Enqueue a background job (idempotent by job_key)."""
    existing_result = await db.execute(select(LockJobReceipt).where(LockJobReceipt.job_key == job_key))
    existing = existing_result.scalars().first()
    if existing:
        return existing

    job = LockJobReceipt(
        job_key=job_key,
        job_type=job_type,
        payload=payload or {},
        run_after=run_after or _now(),
        state="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def claim_jobs(
    db: AsyncSession,
    *,
    worker_id: str,
    job_types: list[str],
    limit: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[LockJobReceipt]:
    """Claim pending jobs using SELECT FOR UPDATE SKIP LOCKED."""
    if now is None:
        now = _now()

    lease_until = now + timedelta(seconds=lease_seconds)

    result = await db.execute(
        select(LockJobReceipt)
        .where(
            LockJobReceipt.state == "pending",
            LockJobReceipt.job_type.in_(job_types),
            LockJobReceipt.run_after <= now,
        )
        .order_by(LockJobReceipt.run_after)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = list(result.scalars().all())

    for job in jobs:
        job.state = "running"
        job.lease_owner = worker_id
        job.lease_until = lease_until
        job.attempts += 1
        job.updated_at = now

    await db.flush()
    return jobs
