from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bot.config import settings

# Создаём основной объект SQLAlchemy - движок (асинхронный).
engine = create_async_engine(
    url=settings.database_url,
    echo=False,
    future=True,  # Новая версия SQLAlchemy 2.x.
)

# Фабрика асинхронных сессий: чтобы у каждого запроса была своя независимая сессия
async_session_maker = sessionmaker(
    engine=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)