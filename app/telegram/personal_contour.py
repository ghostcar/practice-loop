"""Backward-compatibility shim.

All code has been moved to ``app.telegram.pc`` package (10 focused modules).
This module re-exports every public symbol so existing imports keep working.
"""

from __future__ import annotations

# Re-export async_session_factory for test patches
from app.database import async_session_factory  # noqa: F401

# Re-export everything from the new package
from app.telegram.pc import *  # noqa: F401, F403

# Re-export specific handler functions that tests import directly
from app.telegram.pc.games import (  # noqa: F401
    cb_wear_freeze,
    cb_wear_game_dice,
    cb_wear_game_wheel,
    cb_wear_unfreeze,
    msg_challenge_photo,
    msg_challenge_text_fallback,
    msg_wear_inspection_photo,
)
from app.telegram.pc.helpers import (  # noqa: F401
    TAG_TITLES_RU,
    PersonalStates,
    _get_user_by_chat,
    _progress_bar,
    _require_user,
    _try_link_by_code,
    personal_router,
)
from app.telegram.pc.status import _render_user_status_card  # noqa: F401
from app.telegram.pc.wear import _render_wear_card  # noqa: F401
