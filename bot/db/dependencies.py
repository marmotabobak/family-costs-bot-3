from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator

from bot.db.session import async_session_maker

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный менеджер контекста, возвращающий сессию."""

    session = async_session_maker()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
