from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.adaptive_training import AdaptiveProgram, AdaptiveProgramStep  # noqa: E402
from app.models.agency import AgencyLevel, AgencyPolicy  # noqa: E402
from app.models.automation import AutomationTrigger  # noqa: E402
from app.models.body_cycle import BodyCycleLog  # noqa: E402
from app.models.capability import CapabilityGrantV2  # noqa: E402
from app.models.community_agent import (  # noqa: E402
    CommunityMemberDelegation,
    CommunityTopAgent,
    CommunityTournament,
    CommunityTournamentEntry,
)
from app.models.community_leagues import UserLeagueTier  # noqa: E402  # behind experimental_leagues flag
from app.models.community_roles import CommunityMemberRole  # noqa: E402
from app.models.dead_mans_switch import DeadMansSwitchRule  # noqa: E402
from app.models.ds_suite import (  # noqa: E402
    AssignedDuty,
    CapabilityGrant,
    CapabilityGrantClaimAttempt,
    ChastityLockLog,
    ManagedSubmissive,
    WearCheckInLog,
)
from app.models.duels import UserDuel  # noqa: E402
from app.models.dynamic import DynamicDefinition, DynamicRun  # noqa: E402
from app.models.equipment_maintenance import EquipmentMaintenanceLog  # noqa: E402
from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider, LLMUserSelection  # noqa: E402
from app.models.media_exposure import MediaExposureDrop  # noqa: E402
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
from app.models.protocol import (  # noqa: E402
    ProtocolAnchorType,
    ProtocolDefinition,
    ProtocolRun,
    ProtocolStep,
    ProtocolStepLog,
    ProtocolStepType,
    TimingSpecType,
)
from app.models.quest import Quest, UserQuest  # noqa: E402

__all__ = [
    "Base",
    "LLMGlobalModel",
    "LLMGlobalProvider",
    "LLMUserSelection",
    "AdaptiveProgram",
    "AdaptiveProgramStep",
    "AgencyLevel",
    "AgencyPolicy",
    "AssignedDuty",
    "AutomationTrigger",
    "BodyCycleLog",
    "CapabilityGrant",
    "CapabilityGrantClaimAttempt",
    "CapabilityGrantV2",
    "ChastityLockLog",
    "CommunityMemberDelegation",
    "CommunityMemberRole",
    "CommunityTopAgent",
    "CommunityTournament",
    "CommunityTournamentEntry",
    "DeadMansSwitchRule",
    "DynamicDefinition",
    "DynamicRun",
    "EquipmentMaintenanceLog",
    "ManagedSubmissive",
    "MediaExposureDrop",
    "OneTimeMediaToken",
    "PaymentInvoice",
    "PromoCode",
    "PromptLibraryItem",
    "ProtocolAnchorType",
    "ProtocolDefinition",
    "ProtocolRun",
    "ProtocolStep",
    "ProtocolStepLog",
    "ProtocolStepType",
    "Quest",
    "SubscriptionTier",
    "TemporaryFeaturePromotion",
    "TierFeatureGrant",
    "TimingSpecType",
    "UserAgentPersona",
    "UserDuel",
    "UserLeagueTier",
    "UserQuest",
    "WearCheckInLog",
]
