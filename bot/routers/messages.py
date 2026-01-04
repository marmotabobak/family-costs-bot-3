import logging

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bot.constants import HELP_TEXT, MSG_DB_ERROR, MSG_INVALID_LINES, MSG_PARSE_ERROR, MSG_SUCCESS
from bot.db.dependencies import get_session
from bot.db.repositories.messages import save_message
from bot.services.message_parser import parse_message
from bot.utils import pluralize

logger = logging.getLogger(__name__)
router = Router()


@router.message(~Command(commands=["start", "help"]))
async def handle_message(message: Message):
    if not message.text or not message.from_user:
        return

    result = parse_message(message.text)
    if result is None:
        logger.warning("Failed to parse message: user_id=%s, text=%r", message.from_user.id, message.text)
        await message.answer(MSG_PARSE_ERROR)
        await message.answer(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)
        return

    try:
        async with get_session() as session:
            for cost in result.valid_lines:
                text = f"{cost.name} {cost.amount}"
                await save_message(
                    session=session,
                    user_id=message.from_user.id,
                    text=text,
                )
    except Exception:
        logger.exception("Failed to save message: user_id=%s", message.from_user.id)
        await message.answer(MSG_DB_ERROR)
        return

    result_messages = []

    if result.invalid_lines:
        logger.info(
            "Partially parsed message: user_id=%s, invalid_lines=%r",
            message.from_user.id,
            result.invalid_lines,
        )
        invalid_lines = "\n".join(result.invalid_lines)
        result_messages.append(MSG_INVALID_LINES.format(lines=invalid_lines))

    count = len(result.valid_lines)
    logger.debug("%d costs successfully saved", count)
    word = pluralize(count, "расход", "расхода", "расходов")
    result_messages.append(MSG_SUCCESS.format(count=count, word=word))

    await message.answer("\n\n".join(result_messages))
