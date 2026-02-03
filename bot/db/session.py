import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings

logger = logging.getLogger(__name__)

# Configure SQLAlchemy logging
if settings.env.value == "dev":
    # Enable detailed SQL logging in DEV mode
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.INFO)
    echo = True
else:
    echo = False

logger.info(
    "Creating database engine: url=%s, echo=%s, pool_size=10",
    settings.database_url.split("@")[-1] if "@" in settings.database_url else "***",
    echo,
)

engine = create_async_engine(
    settings.database_url,
    echo=echo,
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

logger.info("Database engine and session maker created")
