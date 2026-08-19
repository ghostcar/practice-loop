from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.quest import Quest, UserQuest  # noqa: E402

__all__ = ["Base", "Quest", "UserQuest"]
