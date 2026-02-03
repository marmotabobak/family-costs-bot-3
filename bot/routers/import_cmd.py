import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.web.app import generate_import_token

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("import"))
async def import_command(message: Message):
    """Handle /import command - generate token and send import link."""
    if not message.from_user:
        return

    token = generate_import_token(message.from_user.id)
    import_url = f"{settings.web_base_url}/import/{token}"
    logger.debug("Generated import token for user %s: %s", message.from_user.id, import_url)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Загрузить чеки", url=import_url)]])

    await message.answer(
        "<b>Импорт расходов из ВкусВилл</b>\n\nНажмите кнопку ниже для загрузки:",
        reply_markup=keyboard,
    )
