from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
