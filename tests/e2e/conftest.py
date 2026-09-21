"""Fixtures for e2e tests that use the real database."""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, text

from bot.db.models import ExchangeRate, Message
from bot.db.session import engine


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests that require PostgreSQL when it is not available."""

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
        e2e_dir = str(config.rootpath / "tests" / "e2e")
        for item in items:
            if str(item.fspath).startswith(e2e_dir) and "currency" in str(item.fspath):
                item.add_marker(skip_marker)


@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_db_e2e():
    """Clean the DB before each e2e test that touches the real database.

    Mirrors the integration cleanup_db fixture so that currency-related e2e
    tests start with a predictable state (only RUB as base currency).
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        yield
        return

    from bot.db.dependencies import get_session

    async with get_session() as session:
        await session.execute(delete(Message))
        await session.execute(delete(ExchangeRate))
        await session.execute(text("DELETE FROM currencies WHERE code != 'RUB'"))
        await session.execute(
            text(
                "INSERT INTO currencies (code, is_base, default_rate) "
                "VALUES ('RUB', TRUE, 1) "
                "ON CONFLICT (code) DO UPDATE SET is_base = TRUE, default_rate = 1"
            )
        )
        await session.commit()

    await engine.dispose()

    yield

    await engine.dispose()
