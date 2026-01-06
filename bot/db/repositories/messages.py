from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Message


async def get_unique_user_ids(session: AsyncSession) -> list[int]:
    """Возвращает список уникальных user_id из таблицы сообщений."""
    result = await session.execute(
        select(Message.user_id).distinct().order_by(Message.user_id)
    )
    return list(result.scalars().all())


async def save_message(
    session: AsyncSession,
    user_id: int,
    text: str,
) -> Message:
    """Создает объект сообщения без commit (для batch операций).
    
    Вызывающий код должен сам делать commit.
    Это позволяет сохранять несколько сообщений атомарно в одной транзакции.
    """
    message = Message(
        user_id=user_id,
        text=text,
    )

    session.add(message)
    await session.flush()  # Получаем id и created_at без commit
    await session.refresh(message)

    return message
