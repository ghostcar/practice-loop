from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.adaptive_training import AdaptiveProgram, AdaptiveProgramStep  # noqa: E402
from app.models.automation import AutomationTrigger  # noqa: E402
from app.models.body_cycle import BodyCycleLog  # noqa: E402
from app.models.community_agent import (  # noqa: E402
    CommunityMemberDelegation,
    CommunityTopAgent,
    CommunityTournament,
    CommunityTournamentEntry,
)
from app.models.community_leagues import UserLeagueTier  # noqa: E402
from app.models.community_roles import CommunityMemberRole  # noqa: E402
from app.models.ds_suite import (  # noqa: E402
    AssignedDuty,
    CapabilityGrant,
    CapabilityGrantClaimAttempt,
    ChastityLockLog,
    ManagedSubmissive,
    WearCheckInLog,
)
from app.models.duels import UserDuel  # noqa: E402
from app.models.equipment_maintenance import EquipmentMaintenanceLog  # noqa: E402
from app.models.media_vault import OneTimeMediaToken  # noqa: E402
from app.models.monetization import (  # noqa: E402
    SubscriptionTier,
    TemporaryFeaturePromotion,
    TierFeatureGrant,
)
from app.models.payment import PaymentInvoice  # noqa: E402
from app.models.persona import UserAgentPersona  # noqa: E402
from app.models.promocodes import PromoCode  # noqa: E402
from app.models.prompt_library import PromptLibraryItem  # noqa: E402
from app.models.quest import Quest, UserQuest  # noqa: E402

__all__ = [
    "Base",
    "AdaptiveProgram",
    "AdaptiveProgramStep",
    "AssignedDuty",
    "AutomationTrigger",
    "BodyCycleLog",
    "CapabilityGrant",
    "CapabilityGrantClaimAttempt",
    "ChastityLockLog",
    "CommunityMemberDelegation",
    "CommunityMemberRole",
    "CommunityTopAgent",
    "CommunityTournament",
    "CommunityTournamentEntry",
    "EquipmentMaintenanceLog",
    "ManagedSubmissive",
    "OneTimeMediaToken",
    "PaymentInvoice",
    "PromoCode",
    "PromptLibraryItem",
    "Quest",
    "SubscriptionTier",
    "TemporaryFeaturePromotion",
    "TierFeatureGrant",
    "UserAgentPersona",
    "UserDuel",
    "UserLeagueTier",
    "UserQuest",
    "WearCheckInLog",
]
