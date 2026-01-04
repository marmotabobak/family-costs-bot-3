"""Фикстуры для интеграционных тестов."""

import pytest_asyncio
from sqlalchemy import delete

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.db.session import engine


@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_db():
    """Очищает БД перед каждым тестом для изоляции."""
    # Очищаем БД ПЕРЕД тестом
    async with get_session() as session:
        await session.execute(delete(Message))
        await session.commit()

    yield

    # После теста закрываем все соединения
    await engine.dispose()

