"""Onboarding Service — business logic for new-user setup wizard.

After registration, new users go through a 4-step onboarding:
  1. AI participation mode (none / portal / personal)
  2. Module selection (which features to enable)
  3. LLM setup (only when AI participation is not "none")
  4. Ready → complete → consent → dashboard

Tracks completion via ``user.prefs.onboarding_completed`` (JSONB, no migration).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.prefs import AI_PARTICIPATION, PROFILE_MODULES, sanitize_prefs


def is_onboarding_complete(raw_prefs: dict | None) -> bool:
    """Check if user has completed onboarding.

    Explicitly True = completed. Absent/falsy = incomplete (default path).
    """
    raw = dict(raw_prefs or {})
    return bool(raw.get("onboarding_completed"))


def get_onboarding_context(user) -> dict:
    """Build template context for the onboarding wizard."""
    prefs = sanitize_prefs(user.prefs) if hasattr(user, "prefs") else sanitize_prefs(None)
    enabled = prefs.get("enabled_modules", list(PROFILE_MODULES))
    return {
        "profile_modules": [
            {
                "key": m,
                "label_key": _MODULE_LABEL_KEYS.get(m, m),
                "description_key": _MODULE_DESCRIPTION_KEYS.get(m, m),
                "enabled": m in enabled,
            }
            for m in PROFILE_MODULES
        ],
        "onboarding_completed": prefs.get("onboarding_completed", False),
        "ai_participation": prefs.get("ai_participation", "portal"),
        "ai_participation_options": [
            {
                "key": "none",
                "label_key": _AI_PARTICIPATION_LABELS["none"],
                "description_key": _AI_PARTICIPATION_DESCRIPTIONS["none"],
            },
            {
                "key": "portal",
                "label_key": _AI_PARTICIPATION_LABELS["portal"],
                "description_key": _AI_PARTICIPATION_DESCRIPTIONS["portal"],
            },
            {
                "key": "personal",
                "label_key": _AI_PARTICIPATION_LABELS["personal"],
                "description_key": _AI_PARTICIPATION_DESCRIPTIONS["personal"],
            },
        ],
    }


async def complete_onboarding(
    db: AsyncSession,
    user,
    *,
    enabled_modules: list[str] | None = None,
    ai_participation: str | None = None,
) -> None:
    """Mark onboarding as complete and persist module choices."""
    raw = sanitize_prefs(user.prefs) if hasattr(user, "prefs") else {}
    raw["onboarding_completed"] = True
    if enabled_modules is not None:
        raw["enabled_modules"] = [name for name in PROFILE_MODULES if name in enabled_modules]
    if ai_participation is not None and ai_participation in AI_PARTICIPATION:
        raw["ai_participation"] = ai_participation
    user.prefs = raw
    db.add(user)
    await db.flush()


def should_redirect_to_onboarding(user) -> bool:
    """Check if user should be redirected to onboarding (unfinished)."""
    if not hasattr(user, "prefs"):
        return False
    return not is_onboarding_complete(user.prefs)


# ── AI participation labels / descriptions ──

_AI_PARTICIPATION_LABELS = {
    "none": "onboard_ai_none_label",
    "portal": "onboard_ai_portal_label",
    "personal": "onboard_ai_personal_label",
}

_AI_PARTICIPATION_DESCRIPTIONS = {
    "none": "onboard_ai_none_desc",
    "portal": "onboard_ai_portal_desc",
    "personal": "onboard_ai_personal_desc",
}


# ── Module labels / descriptions ──

_MODULE_LABEL_KEYS = {
    "tracker": "onboard_module_tracker",
    "timer": "onboard_module_timer",
    "medication": "onboard_module_medication",
    "health": "onboard_module_health",
    "journal": "onboard_module_journal",
    "care": "onboard_module_care",
    "catalog": "onboard_module_catalog",
    "insights": "onboard_module_insights",
    "aftercare": "onboard_module_aftercare",
    "social": "onboard_module_social",
}

_MODULE_DESCRIPTION_KEYS = {
    "tracker": "onboard_module_tracker_desc",
    "timer": "onboard_module_timer_desc",
    "medication": "onboard_module_medication_desc",
    "health": "onboard_module_health_desc",
    "journal": "onboard_module_journal_desc",
    "care": "onboard_module_care_desc",
    "catalog": "onboard_module_catalog_desc",
    "insights": "onboard_module_insights_desc",
    "aftercare": "onboard_module_aftercare_desc",
    "social": "onboard_module_social_desc",
}
