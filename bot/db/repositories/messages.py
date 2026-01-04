from bot.db.models import Message
from sqlalchemy.ext.asyncio import AsyncSession


async def save_message(
    session: AsyncSession,
    user_id: int,
    text: str,
) -> Message:
    """Сохраняет сообщение в БД."""

    message = Message(
        user_id=user_id,
        text=text,
    )

    session.add(message)
    await session.commit()
    await session.refresh(message)  # Загружаем id и created_at из БД после коммита.

    return message
