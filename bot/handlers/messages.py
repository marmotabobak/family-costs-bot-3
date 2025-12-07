from aiogram import Router
from aiogram.types import Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import save_message

router = Router()

@router.message()
async def echo_and_save(message: Message) -> None:
    async with get_session() as session:
        await save_message(
            session=session,
            user_id=message.from_user.id,
            text=message.text or "",
        )

        await message.answer("Сообщение сохранено!")