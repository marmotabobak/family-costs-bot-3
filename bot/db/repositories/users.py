from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


async def get_all_users(session: AsyncSession) -> list[User]:
    """Возвращает список всех пользователей, отсортированных по имени."""
    result = await session.execute(select(User).order_by(User.name))
    return list(result.scalars().all())


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Возвращает пользователя по внутреннему ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """Возвращает пользователя по Telegram ID."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, telegram_id: int, name: str) -> User:
    """Создаёт нового пользователя (без commit)."""
    user = User(telegram_id=telegram_id, name=name)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user_id: int, telegram_id: int, name: str) -> User | None:
    """Обновляет пользователя по внутреннему ID (без commit)."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.telegram_id = telegram_id  # type: ignore[assignment]
    user.name = name  # type: ignore[assignment]
    await session.flush()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    """Удаляет пользователя по внутреннему ID (без commit)."""
    result = await session.execute(delete(User).where(User.id == user_id))
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


async def get_all_telegram_ids(session: AsyncSession) -> list[int]:
    """Возвращает список всех Telegram ID зарегистрированных пользователей."""
    result = await session.execute(select(User.telegram_id).order_by(User.telegram_id))
    return list(result.scalars().all())
