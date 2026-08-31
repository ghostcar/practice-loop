"""LockTimer LLM proposals API — C7.

POST /api/v2/locktimer/sessions/{id}/proposals — generate LLM proposal
GET  /api/v2/locktimer/proposals/{id}            — get proposal
POST /api/v2/locktimer/proposals/{id}/items/{item_id}/apply  — apply item
POST /api/v2/locktimer/proposals/{id}/items/{item_id}/reject — reject item
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.llm.client import call_llm
from app.llm.repair import repair_json
from app.locktimer.llm_context import SYSTEM_PROMPT, build_timer_context, format_timer_prompt
from app.locktimer.repositories import get_session
from app.locktimer.services.execution import add_slot_rule, add_task_rule
from app.models.llm_config import LLMProviderConfig
from app.models.locktimer import LockLlmProposal
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/locktimer", tags=["locktimer-proposals"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProposalRequest(BaseModel):
    kind: str = "pre_start_plan"  # pre_start_plan | hidden_reveal | anchor_fill
    user_brief: str | None = None


class ProposalItemApply(BaseModel):
    pass  # body is empty — just marks the item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_proposal_items(raw_items: list, allowed: dict) -> list[dict]:
    """Validate and sanitize LLM-generated proposal items."""
    validated = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        if item_type not in ("slot_rule", "task_rule", "inner_period", "param_override"):
            continue
        validated.append(
            {
                "item_id": str(item.get("item_id", uuid.uuid4())),
                "type": item_type,
                "title": str(item.get("title", ""))[:500],
                "data": item.get("data", {}),
                "reasoning": str(item.get("reasoning", ""))[:1000],
                "status": "pending",
            }
        )
    return validated


async def _get_active_llm_config(db: AsyncSession, user_id: uuid.UUID) -> LLMProviderConfig | None:
    from app.llm.resolver import resolve_llm_config

    return await resolve_llm_config(db, user_id, "text")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/proposals")
async def create_proposal(
    session_id: uuid.UUID,
    body: ProposalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an LLM proposal for a timer session."""
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")

    config = await _get_active_llm_config(db, current_user.id)
    if config is None:
        raise HTTPException(400, "No active LLM provider configured")

    # Build context
    ctx = await build_timer_context(db, session_id, current_user.id)
    user_prompt = format_timer_prompt(ctx, body.user_brief)

    # Call LLM
    try:
        result = await call_llm(config, SYSTEM_PROMPT, user_prompt, json_mode=True)
    except Exception as exc:
        logger.warning("LLM proposal generation failed: %s", exc)
        raise HTTPException(503, f"LLM provider unavailable: {exc}") from exc

    # Parse and validate
    parsed = repair_json(result["content"])
    if not parsed or not isinstance(parsed.get("items"), list):
        raise HTTPException(422, "LLM returned invalid proposal format")

    items = _validate_proposal_items(parsed["items"], {})

    # Store
    proposal = LockLlmProposal(
        session_id=session_id,
        owner_id=current_user.id,
        kind=body.kind,
        user_brief=body.user_brief,
        items=items,
        llm_provider_config_id=config.id,
        llm_model=config.model_name,
        llm_prompt_tokens=result["usage"]["prompt_tokens"],
        llm_completion_tokens=result["usage"]["completion_tokens"],
        llm_cost=result["usage"]["cost"],
    )
    db.add(proposal)
    await db.flush()

    return {
        "id": str(proposal.id),
        "kind": proposal.kind,
        "status": proposal.status,
        "items": proposal.items,
        "usage": result["usage"],
    }


@router.get("/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(LockLlmProposal).where(
            LockLlmProposal.id == proposal_id,
            LockLlmProposal.owner_id == current_user.id,
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(404, "Proposal not found")

    return {
        "id": str(proposal.id),
        "session_id": str(proposal.session_id),
        "kind": proposal.kind,
        "status": proposal.status,
        "user_brief": proposal.user_brief,
        "items": proposal.items,
        "llm_model": proposal.llm_model,
        "usage": {
            "prompt_tokens": proposal.llm_prompt_tokens,
            "completion_tokens": proposal.llm_completion_tokens,
            "cost": float(proposal.llm_cost),
        },
    }


@router.post("/proposals/{proposal_id}/items/{item_id}/apply")
async def apply_proposal_item(
    proposal_id: uuid.UUID,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a single proposal item to the session (draft only)."""
    result = await db.execute(
        select(LockLlmProposal).where(
            LockLlmProposal.id == proposal_id,
            LockLlmProposal.owner_id == current_user.id,
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(404, "Proposal not found")

    # Find the item
    items: list = proposal.items
    item = None
    item_idx = None
    for i, it in enumerate(items):
        if it.get("item_id") == item_id:
            item = it
            item_idx = i
            break

    if item is None:
        raise HTTPException(404, "Item not found in proposal")
    if item.get("status") != "pending":
        raise HTTPException(409, "Item already applied or rejected")

    # Get session — must be draft
    session = await get_session(db, proposal.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != "draft":
        raise HTTPException(409, "Can only apply items to draft sessions")

    # Apply based on type
    item_type = item["type"]
    data = item.get("data", {})

    if item_type == "slot_rule":
        await add_slot_rule(
            db,
            session_id=session.id,
            name=item.get("title", "LLM slot"),
            rule_type=data.get("rule_type", "every_n_days"),
            schedule=data.get("schedule", {"n": 1, "time_of_day": "12:00"}),
            duration_seconds=data.get("duration_seconds", 3600),
            allow_late_open=data.get("allow_late_open", False),
            max_late_seconds=data.get("max_late_seconds", 0),
            extend_on_late_open=data.get("extend_on_late_open", False),
            close_grace_seconds=data.get("close_grace_seconds", 0),
        )
    elif item_type == "task_rule":
        await add_task_rule(
            db,
            session_id=session.id,
            title=item.get("title", "LLM task"),
            schedule_type=data.get("schedule_type", "daily"),
            schedule=data.get("schedule", {"time_of_day": "09:00"}),
            due_window_seconds=data.get("due_window_seconds", 3600),
            requires_report=data.get("requires_report", False),
        )
    # item_type == "inner_period" / "param_override" — deferred to full C7

    # Mark item as applied
    items[item_idx]["status"] = "applied"
    items[item_idx]["applied_at"] = datetime.now(UTC).isoformat()

    # Update proposal status
    all_statuses = {it.get("status") for it in items}
    if "pending" not in all_statuses:
        proposal.status = "applied" if "applied" in all_statuses else "rejected"
    else:
        proposal.status = "partial"

    proposal.items = items

    await db.flush()
    return {"item_id": item_id, "status": "applied", "proposal_status": proposal.status}


@router.post("/proposals/{proposal_id}/items/{item_id}/reject")
async def reject_proposal_item(
    proposal_id: uuid.UUID,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a proposal item."""
    result = await db.execute(
        select(LockLlmProposal).where(
            LockLlmProposal.id == proposal_id,
            LockLlmProposal.owner_id == current_user.id,
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(404, "Proposal not found")

    items: list = proposal.items
    item_idx = None
    for i, it in enumerate(items):
        if it.get("item_id") == item_id:
            item_idx = i
            break

    if item_idx is None:
        raise HTTPException(404, "Item not found in proposal")
    if items[item_idx].get("status") != "pending":
        raise HTTPException(409, "Item already applied or rejected")

    items[item_idx]["status"] = "rejected"

    all_statuses = {it.get("status") for it in items}
    if "pending" not in all_statuses:
        proposal.status = "applied" if "applied" in all_statuses else "rejected"
    else:
        proposal.status = "partial"

    proposal.items = items

    await db.flush()
    return {"item_id": item_id, "status": "rejected", "proposal_status": proposal.status}
