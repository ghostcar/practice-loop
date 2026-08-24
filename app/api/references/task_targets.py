"""Task-targets API — body/location/inventory links, task search, available inventory (REFACTORING.md step 3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.activity_log import ActivityLog
from app.models.body_part import BodyPart, TaskBodyTarget
from app.models.life import InventoryItem
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocation, TaskLocationUsage
from app.models.user import User
from app.schemas.references import (
    TaskBodyTargetBatch,
    TaskBodyTargetOut,
    TaskInventoryUsageBatch,
    TaskInventoryUsageOut,
    TaskLocationUsageBatch,
    TaskLocationUsageOut,
)

router = APIRouter(tags=["task-targets"])


async def _get_owned_task(db: AsyncSession, task_id: uuid.UUID, user: User) -> ActivityLog:
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == task_id, ActivityLog.user_id == user.id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/tasks/{task_id}/body-targets", response_model=list[TaskBodyTargetOut])
async def list_task_body_targets(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskBodyTarget)
        .where(TaskBodyTarget.task_id == task.id)
        .order_by(TaskBodyTarget.sort_order, TaskBodyTarget.created_at)
    )
    return [TaskBodyTargetOut.model_validate(t) for t in result.scalars().all()]


@router.post("/tasks/{task_id}/body-targets", response_model=list[TaskBodyTargetOut])
async def set_task_body_targets(
    task_id: uuid.UUID,
    data: TaskBodyTargetBatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace all body targets for a task atomically."""
    task = await _get_owned_task(db, task_id, user)

    # Delete existing
    await db.execute(delete(TaskBodyTarget).where(TaskBodyTarget.task_id == task.id))

    # Create new
    created: list[TaskBodyTarget] = []
    for t in data.targets:
        snapshot = ""
        if t.body_part_id:
            bp_result = await db.execute(select(BodyPart.title_ru).where(BodyPart.id == t.body_part_id))
            bp_title = bp_result.scalar_one_or_none()
            snapshot = bp_title or str(t.body_part_id)
        else:
            snapshot = "—"

        link = TaskBodyTarget(
            task_id=task.id,
            body_part_id=t.body_part_id,
            target_role=t.target_role,
            side=t.side,
            planned_intensity=t.planned_intensity,
            actual_intensity=t.actual_intensity,
            planned_duration_seconds=t.planned_duration_seconds,
            actual_duration_seconds=t.actual_duration_seconds,
            sort_order=t.sort_order,
            body_part_name_snapshot=snapshot,
            planned_notes=t.planned_notes,
            actual_notes=t.actual_notes,
        )
        db.add(link)
        await db.flush()
        created.append(link)
    for link in created:
        await db.refresh(link)
    return [TaskBodyTargetOut.model_validate(link) for link in created]


@router.delete("/tasks/{task_id}/body-targets/{target_id}")
async def delete_task_body_target(
    task_id: uuid.UUID,
    target_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskBodyTarget).where(TaskBodyTarget.id == target_id, TaskBodyTarget.task_id == task.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "Body target not found")

    await db.delete(target)
    return {"status": "deleted"}


@router.get("/tasks/{task_id}/location-usages", response_model=list[TaskLocationUsageOut])
async def list_task_location_usages(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskLocationUsage)
        .where(TaskLocationUsage.task_id == task.id)
        .order_by(TaskLocationUsage.sort_order, TaskLocationUsage.created_at)
    )
    return [TaskLocationUsageOut.model_validate(u) for u in result.scalars().all()]


@router.post("/tasks/{task_id}/location-usages", response_model=list[TaskLocationUsageOut])
async def set_task_location_usages(
    task_id: uuid.UUID,
    data: TaskLocationUsageBatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace all location usages for a task atomically."""
    task = await _get_owned_task(db, task_id, user)

    await db.execute(delete(TaskLocationUsage).where(TaskLocationUsage.task_id == task.id))

    created: list[TaskLocationUsage] = []
    for u in data.usages:
        snapshot = ""
        if u.location_id:
            loc_result = await db.execute(select(TaskLocation.title_ru).where(TaskLocation.id == u.location_id))
            loc_title = loc_result.scalar_one_or_none()
            snapshot = loc_title or str(u.location_id)
        else:
            snapshot = "—"

        link = TaskLocationUsage(
            task_id=task.id,
            location_id=u.location_id,
            location_role=u.location_role,
            is_required=u.is_required,
            sort_order=u.sort_order,
            location_name_snapshot=snapshot,
            planned_notes=u.planned_notes,
            actual_notes=u.actual_notes,
        )
        db.add(link)
        await db.flush()
        created.append(link)
    for link in created:
        await db.refresh(link)
    return [TaskLocationUsageOut.model_validate(link) for link in created]


@router.delete("/tasks/{task_id}/location-usages/{usage_id}")
async def delete_task_location_usage(
    task_id: uuid.UUID,
    usage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskLocationUsage).where(TaskLocationUsage.id == usage_id, TaskLocationUsage.task_id == task.id)
    )
    usage = result.scalar_one_or_none()
    if usage is None:
        raise HTTPException(404, "Location usage not found")

    await db.delete(usage)
    return {"status": "deleted"}


@router.get("/tasks/{task_id}/inventory-usages", response_model=list[TaskInventoryUsageOut])
async def list_task_inventory_usages(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskInventoryUsage)
        .where(TaskInventoryUsage.task_id == task.id)
        .order_by(TaskInventoryUsage.sort_order, TaskInventoryUsage.created_at)
    )
    return [TaskInventoryUsageOut.model_validate(u) for u in result.scalars().all()]


@router.post("/tasks/{task_id}/inventory-usages", response_model=list[TaskInventoryUsageOut])
async def set_task_inventory_usages(
    task_id: uuid.UUID,
    data: TaskInventoryUsageBatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace all inventory usages for a task atomically."""
    task = await _get_owned_task(db, task_id, user)

    await db.execute(delete(TaskInventoryUsage).where(TaskInventoryUsage.task_id == task.id))

    created: list[TaskInventoryUsage] = []
    for u in data.usages:
        snapshot = ""
        cat_snapshot: str | None = None
        if u.inventory_item_id:
            item_result = await db.execute(
                select(InventoryItem.name, InventoryItem.category).where(
                    InventoryItem.id == u.inventory_item_id, InventoryItem.user_id == user.id
                )
            )
            row = item_result.one_or_none()
            if row:
                snapshot = row[0]
                cat_snapshot = row[1]
            else:
                snapshot = str(u.inventory_item_id)
        else:
            snapshot = "—"

        link = TaskInventoryUsage(
            task_id=task.id,
            inventory_item_id=u.inventory_item_id,
            usage_role=u.usage_role,
            planned_quantity=u.planned_quantity,
            actual_quantity=u.actual_quantity,
            unit=u.unit,
            is_required=u.is_required,
            sort_order=u.sort_order,
            inventory_name_snapshot=snapshot,
            inventory_category_snapshot=cat_snapshot,
            planned_notes=u.planned_notes,
            actual_notes=u.actual_notes,
        )
        db.add(link)
        await db.flush()
        created.append(link)
    for link in created:
        await db.refresh(link)
    return [TaskInventoryUsageOut.model_validate(link) for link in created]


@router.delete("/tasks/{task_id}/inventory-usages/{usage_id}")
async def delete_task_inventory_usage(
    task_id: uuid.UUID,
    usage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, user)
    result = await db.execute(
        select(TaskInventoryUsage).where(TaskInventoryUsage.id == usage_id, TaskInventoryUsage.task_id == task.id)
    )
    usage = result.scalar_one_or_none()
    if usage is None:
        raise HTTPException(404, "Inventory usage not found")

    await db.delete(usage)
    return {"status": "deleted"}


@router.get("/inventory/available")
async def list_available_inventory(
    inventory_category_id: uuid.UUID | None = Query(default=None),
    inventory_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List inventory items available for task assignment.

    Excludes archived/unavailable items by default. Filters by category or status.
    """
    query = select(InventoryItem).where(
        InventoryItem.user_id == user.id,
        ~InventoryItem.inventory_status.in_(["archived", "unavailable"]),
    )
    if inventory_category_id:
        query = query.where(InventoryItem.inventory_category_id == inventory_category_id)
    if inventory_status:
        query = query.where(InventoryItem.inventory_status == inventory_status)
    query = query.order_by(InventoryItem.sort_order, InventoryItem.name)

    result = await db.execute(query)

    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "category": i.category,
            "inventory_category_id": str(i.inventory_category_id) if i.inventory_category_id else None,
            "inventory_status": i.inventory_status,
            "status": i.status,
            "image_path": i.image_path,
            "quantity": i.quantity,
            "sort_order": i.sort_order,
        }
        for i in items
    ]


@router.get("/tasks/search")
async def search_tasks(
    status: str | None = Query(default=None),
    body_part_id: uuid.UUID | None = Query(default=None),
    body_system: str | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    location_type: str | None = Query(default=None),
    inventory_item_id: uuid.UUID | None = Query(default=None),
    inventory_category_slug: str | None = Query(default=None),
    session_id: uuid.UUID | None = Query(default=None),
    training_day_id: uuid.UUID | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search tasks with rich filters: body zone, location, inventory, status, date."""
    from sqlalchemy import exists

    query = select(ActivityLog).where(ActivityLog.user_id == user.id)

    # Status filter
    if status:
        query = query.where(ActivityLog.status == status)

    # Body part filter — via TaskBodyTarget
    if body_part_id:
        query = query.where(
            exists()
            .where(
                TaskBodyTarget.task_id == ActivityLog.id,
                TaskBodyTarget.body_part_id == body_part_id,
            )
            .correlate(ActivityLog)
        )
    if body_system:
        query = query.where(
            exists()
            .where(
                TaskBodyTarget.task_id == ActivityLog.id,
                TaskBodyTarget.body_part_id == BodyPart.id,
                BodyPart.body_system == body_system,
            )
            .correlate(ActivityLog)
        )

    # Location filter — via TaskLocationUsage
    if location_id:
        query = query.where(
            exists()
            .where(
                TaskLocationUsage.task_id == ActivityLog.id,
                TaskLocationUsage.location_id == location_id,
            )
            .correlate(ActivityLog)
        )
    if location_type:
        query = query.where(
            exists()
            .where(
                TaskLocationUsage.task_id == ActivityLog.id,
                TaskLocationUsage.location_id == TaskLocation.id,
                TaskLocation.location_type == location_type,
            )
            .correlate(ActivityLog)
        )

    # Inventory filter — via TaskInventoryUsage
    if inventory_item_id:
        query = query.where(
            exists()
            .where(
                TaskInventoryUsage.task_id == ActivityLog.id,
                TaskInventoryUsage.inventory_item_id == inventory_item_id,
            )
            .correlate(ActivityLog)
        )
    if inventory_category_slug:
        query = query.where(
            exists()
            .where(
                TaskInventoryUsage.task_id == ActivityLog.id,
                TaskInventoryUsage.inventory_category_snapshot == inventory_category_slug,
            )
            .correlate(ActivityLog)
        )

    # Session / Training
    if session_id:
        query = query.where(ActivityLog.session_id == session_id)
    if training_day_id:
        query = query.where(ActivityLog.training_day_id == training_day_id)

    # Date range
    if date_from:
        try:
            from datetime import datetime as dt

            df = dt.fromisoformat(date_from)
            query = query.where(ActivityLog.created_at >= df)
        except ValueError:
            raise HTTPException(400, "Invalid date_from format (use ISO 8601)") from None
    if date_to:
        try:
            from datetime import datetime as dt

            dt_val = dt.fromisoformat(date_to)
            query = query.where(ActivityLog.created_at <= dt_val)
        except ValueError:
            raise HTTPException(400, "Invalid date_to format (use ISO 8601)") from None

    # Order & paginate
    query = query.order_by(ActivityLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "entity_id": str(t.entity_id) if t.entity_id else None,
            "status": t.status,
            "title_override": t.title_override,
            "selected_entity_name": t.selected_entity_name,
            "selected_params": t.selected_params,
            "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "session_id": str(t.session_id) if t.session_id else None,
            "training_day_id": str(t.training_day_id) if t.training_day_id else None,
            "points_awarded": t.points_awarded,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]
