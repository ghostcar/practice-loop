"""API Router for Calendar iCal Feed & Export (Step 3 / RFC 5545)."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.community_agent import CommunityTournament
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar_v2"])


@router.get("/feed.ics", response_class=Response)
async def calendar_ical_feed_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates RFC 5545 iCalendar (.ics) feed for user duties & active tournaments."""
    tournaments_res = await db.execute(select(CommunityTournament).where(CommunityTournament.status == "active"))
    tournaments = tournaments_res.scalars().all()

    now_str = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PracticeLoop//Calendar Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:PracticeLoop Calendar",
    ]

    for t in tournaments:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:tournament-{t.id}@practiceloop",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{t.starts_at.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{t.ends_at.strftime('%Y%m%dT%H%M%SZ')}",
                f"SUMMARY:🏆 Турнир: {t.title}",
                f"DESCRIPTION:{t.description}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    ical_content = "\r\n".join(lines)

    return Response(content=ical_content, media_type="text/calendar")
