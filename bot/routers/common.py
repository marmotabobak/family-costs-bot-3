from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bot.constants import HELP_TEXT, START_GREETING

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
