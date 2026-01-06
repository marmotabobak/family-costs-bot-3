from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    # Connection pool настройки для production
    pool_size=10,  # Количество постоянных соединений
    max_overflow=20,  # Дополнительные соединения при пиках (итого до 30)
    pool_timeout=30,  # Таймаут ожидания соединения (секунды)
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,  # Переподключение через час (защита от stale connections)
)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
