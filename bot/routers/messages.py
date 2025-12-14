import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import save_message
from bot.routers.common import HELP_TEXT
from bot.services.message_parser import parse_message

logger = logging.getLogger(__name__)
router = Router()

@router.message(~Command(commands=["start", "help"]))
async def handle_message(message: Message):
    if not message.text or not message.from_user:
        return

    result = parse_message(message.text)
    if result is None:
        logger.error("Failed to parse message: %r",message.text)
        await message.answer("❌ Не удалось распарсить сообщение.")
        await message.answer(HELP_TEXT)
        return

    async with get_session() as session:
        for cost in result.costs:
            text = f"{cost.name} {cost.amount}"
            await save_message(
                session=session,
                user_id=message.from_user.id,
                text=text,
            )

    if result.invalid_lines:
        invalid_costs = "\n".join(f"{line}" for line in result.invalid_lines)
        logger.warning("️Failed to parse costs: %r", invalid_costs)
        await message.answer(f"⚠️ Не удалось распарсить расходы:\n{invalid_costs}")

    if valid_costs_count := len(result.costs):
        logger.debug(f"[{valid_costs_count}] costs successfully saved.")
        await message.answer(f"✅ {valid_costs_count} расходов успешно сохранены.")
