"""Фикстуры для интеграционных тестов."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, text

from bot.db.dependencies import get_session
from bot.db.models import ExchangeRate, Message
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
    """Очищает БД перед каждым тестом для изоляции.

    Deletion order respects FK constraints:
    1. ``messages``          — references ``currencies``
    2. ``exchange_rates``    — references ``currencies``
    3. ``currencies``        — root table (but we keep RUB so the bot works;
       tests that need a clean slate should delete currencies themselves)

    The base RUB currency is **re-inserted** if missing, so tests that delete
    it can rely on the fixture to restore it.
    """
    # Очищаем БД ПЕРЕД тестом
    async with get_session() as session:
        await session.execute(delete(Message))
        await session.execute(delete(ExchangeRate))
        # Delete non-RUB currencies; keep or restore RUB as base
        await session.execute(
            text("DELETE FROM currencies WHERE code != 'RUB'")
        )
        # Ensure RUB exists as the single base currency
        await session.execute(
            text(
                "INSERT INTO currencies (code, is_base, default_rate) "
                "VALUES ('RUB', TRUE, 1) "
                "ON CONFLICT (code) DO UPDATE SET is_base = TRUE, default_rate = 1"
            )
        )
        await session.commit()

    # Dispose pool BEFORE yielding so that TestClient (anyio loop) can create
    # fresh connections without hitting asyncpg connections from pytest's loop.
    await engine.dispose()

    yield

    # Teardown: clear pool again after the test.
    await engine.dispose()
