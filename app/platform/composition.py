"""Product composition and module registry (03A_PRODUCT_VARIANTS.md, 04_DESIGN.md §1–4).

On startup the application builds an immutable `ProductComposition` from
`APP_PRODUCT_VARIANT` and feature flags.  All route, navigation, and job
registrations consult this object — never scattered env checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain module descriptors
# ---------------------------------------------------------------------------

_MODULE_TRACKER = "tracker"
_MODULE_TIMER = "timer"
_MODULE_PLATFORM = "platform"


@dataclass(frozen=True)
class ProductComposition:
    """Immutable composition built once at startup.

    Access this through the module-level singleton, never by calling
    the constructor directly.
    """

    variant: str  # "tracker" | "timer" | "combined"
    enabled_modules: frozenset[str]

    # Operational feature gates (staged rollout, 03A §4/7).
    locktimer_core_enabled: bool = False
    locktimer_verification_enabled: bool = False
    social_enabled: bool = False
    social_tracker_adapter_enabled: bool = False
    social_timer_adapter_enabled: bool = False
    social_public_enabled: bool = False
    locktimer_keyholder_enabled: bool = False
    locktimer_cloud_media_enabled: bool = False
    medication_enabled: bool = True
    health_enabled: bool = True

    # Migration sequence numbers for debugging
    tracker_active: bool = field(init=False)
    timer_active: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracker_active", _MODULE_TRACKER in self.enabled_modules)
        object.__setattr__(self, "timer_active", _MODULE_TIMER in self.enabled_modules)

    @property
    def timer_operational(self) -> bool:
        """Timer routes/jobs allowed right now (flag gate on top of variant)."""
        return self.timer_active and self.locktimer_core_enabled

    @property
    def social_operational(self) -> bool:
        """Platform Social routes/jobs allowed right now."""
        return self.social_enabled


def _resolve_enabled_modules(variant: str) -> frozenset[str]:
    """Map variant string → immutable set of enabled domain modules."""
    if variant == "tracker":
        return frozenset({_MODULE_PLATFORM, _MODULE_TRACKER})
    if variant == "timer":
        return frozenset({_MODULE_PLATFORM, _MODULE_TIMER})
    # combined
    return frozenset({_MODULE_PLATFORM, _MODULE_TRACKER, _MODULE_TIMER})


def build_product_composition() -> ProductComposition:
    """Create the singleton composition from current configuration.

    Called once in app startup (lifespan); never re-evaluated at runtime.
    Raises ValueError for invalid / contradictory configuration.
    """
    variant = settings.app_product_variant  # already validated by pydantic
    enabled_modules = _resolve_enabled_modules(variant)

    logger.info(
        "ProductComposition: variant=%s modules=%s timer_core=%s social=%s",
        variant,
        sorted(enabled_modules),
        settings.locktimer_core_enabled,
        settings.social_enabled,
    )

    return ProductComposition(
        variant=variant,
        enabled_modules=enabled_modules,
        locktimer_core_enabled=settings.locktimer_core_enabled,
        locktimer_verification_enabled=settings.locktimer_verification_enabled,
        social_enabled=settings.social_enabled,
        social_tracker_adapter_enabled=settings.social_tracker_adapter_enabled,
        social_timer_adapter_enabled=settings.social_timer_adapter_enabled,
        social_public_enabled=settings.social_public_enabled,
        locktimer_keyholder_enabled=settings.locktimer_keyholder_enabled,
        locktimer_cloud_media_enabled=settings.locktimer_cloud_media_enabled,
        medication_enabled=settings.medication_enabled,
        health_enabled=settings.health_enabled,
    )


# Module-level singleton — populated by main.py lifespan.
composition: ProductComposition | None = None


def get_composition() -> ProductComposition:
    """Return the current composition (must be initialised)."""
    assert composition is not None, "ProductComposition not initialised"
    return composition
