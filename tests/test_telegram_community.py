"""Integration tests for Telegram Bot Community Top Agent & Tournament Commands."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    create_community_tournament,
    join_community_tournament,
)
from app.models.community_agent import Community, CommunityMemberDelegation
from app.models.user import User
from app.telegram.community_handlers import (
    handle_ds_status_command,
    handle_my_rank_command,
    handle_tournaments_command,
)


@pytest.mark.asyncio
async def test_cmd_tournaments(db_session: AsyncSession, test_user: User):
    """Verify /tournaments handler replies with active public community tournaments."""
    test_user.telegram_chat_id = 99887766
    community = Community(name="Comm T", slug="comm-t", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    await create_community_tournament(db_session, community.id, title="Кубок Осени", metric_type="care", days=7)
    await db_session.commit()

    mock_msg = MagicMock()
    mock_msg.chat.id = 99887766
    mock_msg.answer = AsyncMock()

    await handle_tournaments_command(mock_msg, db=db_session)

    mock_msg.answer.assert_called_once()
    reply_text = mock_msg.answer.call_args[0][0]
    assert "Кубок Осени" in reply_text


@pytest.mark.asyncio
async def test_cmd_my_rank(db_session: AsyncSession, test_user: User):
    """Verify /my_rank handler replies with user tournament rank."""
    test_user.telegram_chat_id = 99887755
    community = Community(name="Comm R", slug="comm-r", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    t = await create_community_tournament(db_session, community.id, title="Кубок Зимы", metric_type="chastity", days=14)
    await join_community_tournament(db_session, t.id, test_user.id)
    await db_session.commit()

    mock_msg = MagicMock()
    mock_msg.chat.id = 99887755
    mock_msg.answer = AsyncMock()

    await handle_my_rank_command(mock_msg, db=db_session)

    mock_msg.answer.assert_called_once()
    reply_text = mock_msg.answer.call_args[0][0]
    assert "Ранг #1" in reply_text


@pytest.mark.asyncio
async def test_cmd_ds_status(db_session: AsyncSession, test_user: User):
    """Verify /ds_status handler replies with D/s compliance status."""
    test_user.telegram_chat_id = 99887744
    community = Community(name="Comm DS", slug="comm-ds", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    delegation = CommunityMemberDelegation(
        community_id=community.id,
        user_id=test_user.id,
        compliance_score=95.5,
    )
    db_session.add(delegation)
    await db_session.commit()

    mock_msg = MagicMock()
    mock_msg.chat.id = 99887744
    mock_msg.answer = AsyncMock()

    await handle_ds_status_command(mock_msg, db=db_session)

    mock_msg.answer.assert_called_once()
    reply_text = mock_msg.answer.call_args[0][0]
    assert "95.5%" in reply_text
