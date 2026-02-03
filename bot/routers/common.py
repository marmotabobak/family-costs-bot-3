from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bot.constants import HELP_TEXT, START_GREETING
from bot.web.app import generate_import_token

router = Router()


@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        START_GREETING + HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("help"))
async def help_(message: Message):
    await message.answer(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("import"))
async def import_command(message: Message):
    """Generate import token and send link to user."""
    if not message.from_user:
        return

    token = generate_import_token(message.from_user.id)
    import_url = f"https://marmota-bobak.ru/family-costs-bot/import/vkusvill/{token}"

    await message.answer(
        f"📥 Импорт чеков из ВкусВилл\n\n"
        f"Перейдите по ссылке для загрузки файла:\n"
        f"{import_url}",
        parse_mode=ParseMode.MARKDOWN,
    )
