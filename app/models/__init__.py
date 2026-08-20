from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.adaptive_training import AdaptiveProgram, AdaptiveProgramStep  # noqa: E402
from app.models.body_cycle import BodyCycleLog  # noqa: E402
from app.models.prompt_library import PromptLibraryItem  # noqa: E402
from app.models.quest import Quest, UserQuest  # noqa: E402

__all__ = [
    "Base",
    "AdaptiveProgram",
    "AdaptiveProgramStep",
    "BodyCycleLog",
    "PromptLibraryItem",
    "Quest",
    "UserQuest",
]
