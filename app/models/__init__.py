from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.prompt_library import PromptLibraryItem  # noqa: E402
from app.models.quest import Quest, UserQuest  # noqa: E402

__all__ = ["Base", "PromptLibraryItem", "Quest", "UserQuest"]
