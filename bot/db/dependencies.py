import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator

from bot.db.session import async_session_maker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный менеджер контекста, возвращающий сессию."""

    session = async_session_maker()
    logger.debug("get_session: created new session")
    try:
        yield session
    except Exception as e:
        logger.error("get_session: exception occurred, rolling back - error=%s", e, exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()
        logger.debug("get_session: session closed")
