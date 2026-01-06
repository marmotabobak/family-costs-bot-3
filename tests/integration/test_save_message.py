import pytest

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.db.repositories.messages import save_message
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_save_message():
    user_id = 123
    text = "Hello, world!"

    async with get_session() as session:
        message = await save_message(session, user_id, text)
        await session.commit()

    # 1. Целостность
    assert message.id is not None
    assert message.created_at is not None

    # 2. Типы
    assert isinstance(message, Message)
    assert isinstance(message.user_id, int)
    assert isinstance(message.created_at, datetime)

    # 3. Значения
    assert message.user_id == user_id
    assert message.text == text

    # 4. created_at
    assert message.created_at.tzinfo is not None
    now = datetime.now(timezone.utc)
    assert abs((now - message.created_at).total_seconds()) < 5, "created_at далеко от текущего времени"
