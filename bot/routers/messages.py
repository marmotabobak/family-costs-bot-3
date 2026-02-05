import logging
import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.exc import SQLAlchemyError

from bot.constants import (
    HELP_TEXT,
    MSG_DB_ERROR,
    MSG_PARSE_ERROR,
    MSG_MESSAGE_MAX_LENGTH,
    MSG_MESSAGE_MAX_LINE_LENGTH,
    MSG_MESSAGE_MAX_LINES_COUNT
)
from bot.db.dependencies import get_session
from bot.db.repositories.messages import save_message
from bot.services.message_parser import Cost, parse_message
from bot.utils import format_amount, pluralize
from bot.exceptions import MessageMaxLineLengthExceed, MessageMaxLengthExceed, MessageMaxLinesCountExceed


logger = logging.getLogger(__name__)
router = Router()

CALLBACK_CONFIRM = "confirm_save"
CALLBACK_CANCEL = "cancel_save"

# =====================
# FSM
# =====================

class SaveCostsStates(StatesGroup):
    waiting_confirmation = State()


# =====================
# KEYBOARDS
# =====================

def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, записать", callback_data=CALLBACK_CONFIRM),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data=CALLBACK_CANCEL),
        ]
    ])


# =====================
# HELPERS
# =====================

def esc(text: str) -> str:
    """HTML-экранирование пользовательского ввода."""
    return html.escape(text, quote=False)


def format_confirmation_message(
    valid_costs: list[Cost],
    invalid_lines: list[str],
) -> str:
    lines: list[str] = []

    if invalid_lines:
        lines.append("⚠️ <b>Не удалось распарсить строки:</b>")
        lines.append("")
        for line in invalid_lines:
            lines.append(f"• {esc(line)}")
        lines.append("")

    lines.append("<b>Успешно распарсены строки:</b>")
    lines.append("")
    for cost in valid_costs:
        lines.append(f"• {esc(cost.name)}: {format_amount(cost.amount, sep='_')}")

    lines.append("")
    lines.append("Записать распарсенные строки?")

    return "\n".join(lines)


def format_success_message(costs: list[Cost]) -> str:
    count = len(costs)
    word = pluralize(count, "расход", "расхода", "расходов")

    lines = [f"✅ <b>Записано {count} {word}:</b>", ""]
    for cost in costs:
        lines.append(f"• {esc(cost.name)}: {format_amount(cost.amount, sep='_')}")

    return "\n".join(lines)


async def save_costs_to_db(user_id: int, costs: list[Cost]) -> bool:
    """Save costs to DB. Returns True on success."""
    async with get_session() as session:
        try:
            for cost in costs:
                await save_message(
                    session=session,
                    user_id=user_id,
                    text=f"{cost.name} {cost.amount}",
                )
            await session.commit()
            return True
        except SQLAlchemyError:
            logger.exception("DB error while saving costs")
            await session.rollback()
            return False


# =====================
# MESSAGE HANDLER
# =====================

@router.message(~Command(commands=["start", "help", "menu", "import"]))
async def handle_message(message: Message, state: FSMContext):
    if not message.text or not message.from_user:
        return

    logger.debug(
        "Received message from user %s: %s",
        message.from_user.id,
        message.text[:50] + "..." if len(message.text) > 50 else message.text,
    )

    try:
        result = parse_message(message.text)
    except MessageMaxLinesCountExceed:
        await message.answer(MSG_MESSAGE_MAX_LINES_COUNT)
        return
    except MessageMaxLengthExceed:
        await message.answer(MSG_MESSAGE_MAX_LENGTH)
        return
    except MessageMaxLineLengthExceed as e:
        await message.answer(f"{MSG_MESSAGE_MAX_LINE_LENGTH} {str(e)[:30]}...")
        return

    if not result:
        await message.answer(MSG_PARSE_ERROR)
        await message.answer(HELP_TEXT)
        return

    # Есть нераспарсенные строки → подтверждение
    if result.invalid_lines:
        await state.set_state(SaveCostsStates.waiting_confirmation)
        await state.update_data(
            valid_costs=result.valid_lines,
            invalid_lines=result.invalid_lines,
        )

        await message.answer(
            format_confirmation_message(
                result.valid_lines,
                result.invalid_lines,
            ),
            reply_markup=build_confirmation_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    # Всё распарсилось → сохраняем сразу
    success = await save_costs_to_db(message.from_user.id, result.valid_lines)

    if not success:
        await message.answer(MSG_DB_ERROR)
        return

    logger.debug("Saved %d costs for user %s", len(result.valid_lines), message.from_user.id)

    await message.answer(
        format_success_message(result.valid_lines),
        parse_mode=ParseMode.HTML,
    )


# =====================
# CALLBACKS
# =====================

@router.callback_query(F.data == CALLBACK_CONFIRM, SaveCostsStates.waiting_confirmation)
async def handle_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    valid_costs: list[Cost] = data.get("valid_costs", [])

    if not valid_costs:
        await callback.answer("Нет данных")
        await state.clear()
        return

    success = await save_costs_to_db(callback.from_user.id, valid_costs)

    if not success:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(MSG_DB_ERROR)
        else:
            await callback.answer(MSG_DB_ERROR, show_alert=True)
        return

    await state.clear()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(format_success_message(valid_costs))
    else:
        await callback.answer(format_success_message(valid_costs))


@router.callback_query(F.data == CALLBACK_CANCEL, SaveCostsStates.waiting_confirmation)
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ Галя, отмена! Исправьте строки и отправьте сообщение снова."
        )
    else:
        await callback.answer("❌ Галя, отмена! Исправьте строки и отправьте сообщение снова.")
