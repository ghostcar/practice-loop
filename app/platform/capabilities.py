"""GET /api/v1/platform/capabilities — versioned discovery endpoint (03A §4, 06 §1)."""

from __future__ import annotations

from fastapi import APIRouter

from app.platform.composition import get_composition

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


@router.get("/capabilities")
async def capabilities():
    """Return product variant, enabled modules, social stage, and API versions.

    Does NOT leak flags, provider configuration, or private object presence.
    """
    comp = get_composition()
    social_stage = "off"
    if comp.social_enabled:
        social_stage = "public" if comp.social_public_enabled else "relationship_only"

    timer_stage = "off"
    if comp.timer_active:
        timer_stage = "operational" if comp.timer_operational else "disabled"

    return {
        "product_variant": comp.variant,
        "enabled_modules": sorted(comp.enabled_modules),
        "social_stage": social_stage,
        "timer_stage": timer_stage,
        "api_versions": {
            "platform": "1",
            "locktimer": "1" if comp.timer_active else None,
            "social": "1" if comp.social_enabled else None,
        },
    }
