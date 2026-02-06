"""Фикстуры для интеграционных тестов."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, text

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.db.session import engine


def pytest_collection_modifyitems(config, items):
    """Skip all integration tests if PostgreSQL is not available."""
    import asyncio

    async def _check_db():
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    db_available = asyncio.run(_check_db())
    if not db_available:
        skip_marker = pytest.mark.skip(reason="PostgreSQL not available")
        integration_dir = str(config.rootpath / "tests" / "integration")
        for item in items:
            if str(item.fspath).startswith(integration_dir):
                item.add_marker(skip_marker)


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
