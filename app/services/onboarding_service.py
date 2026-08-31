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
                "label": _MODULE_LABELS.get(m, m.capitalize()),
                "description": _MODULE_DESCRIPTIONS.get(m, ""),
                "enabled": m in enabled,
            }
            for m in PROFILE_MODULES
        ],
        "onboarding_completed": prefs.get("onboarding_completed", False),
        "ai_participation": prefs.get("ai_participation", "portal"),
        "ai_participation_options": [
            {
                "key": "none",
                "label": _AI_PARTICIPATION_LABELS["none"],
                "description": _AI_PARTICIPATION_DESCRIPTIONS["none"],
            },
            {
                "key": "portal",
                "label": _AI_PARTICIPATION_LABELS["portal"],
                "description": _AI_PARTICIPATION_DESCRIPTIONS["portal"],
            },
            {
                "key": "personal",
                "label": _AI_PARTICIPATION_LABELS["personal"],
                "description": _AI_PARTICIPATION_DESCRIPTIONS["personal"],
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
    "none": "Without AI",
    "portal": "Portal AI (recommended)",
    "personal": "My own key (BYOK)",
}

_AI_PARTICIPATION_DESCRIPTIONS = {
    "none": "Manual task entry only. No auto-generation, no analysis. You can enable AI later in Settings.",
    "portal": "Use deployment-managed providers. No key needed from you. Some may be a paid service.",
    "personal": "Bring your own API key. Your key is encrypted and never shared. Full control over usage and cost.",
}


# ── Module labels / descriptions ──

_MODULE_LABELS = {
    "tracker": "Task Tracker",
    "timer": "Lock Timer",
    "medication": "Medication",
    "health": "Health",
    "journal": "Journal",
    "care": "Care",
    "catalog": "Catalog",
    "insights": "Insights",
    "aftercare": "Aftercare",
    "social": "Social Network",
}

_MODULE_DESCRIPTIONS = {
    "tracker": "Generate and complete daily tasks with LLM assistance.",
    "timer": "Timer-based lock sessions with device binding.",
    "medication": "Track medication courses and adherence.",
    "health": "Log health state, body measurements, and labs.",
    "journal": "Personal journal entries and partner dynamics.",
    "care": "Care products, routines, and aftercare checklists.",
    "catalog": "Browse and manage task catalog with opt-in preferences.",
    "insights": "Analytics, correlation matrix, and medical export.",
    "aftercare": "Aftercare planning and comfort routines.",
    "social": "Public profile, feeds, leaderboards, and community features.",
}
