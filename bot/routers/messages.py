import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.exc import SQLAlchemyError

from bot.constants import HELP_TEXT, MSG_DB_ERROR, MSG_PARSE_ERROR, MSG_SUCCESS
from bot.db.dependencies import get_session
from bot.db.repositories.messages import save_message
from bot.services.message_parser import Cost, parse_message
from bot.utils import pluralize

# Названия месяцев (дублируем из menu.py для независимости)
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

logger = logging.getLogger(__name__)
router = Router()

# Callback data для подтверждения
CALLBACK_CONFIRM_SAVE = "confirm_save"
CALLBACK_CANCEL_SAVE = "cancel_save"
CALLBACK_DISABLE_PAST = "disable_past"  # отключить режим ввода в прошлое


class SaveCostsStates(StatesGroup):
    """Состояния FSM для сохранения расходов."""

    waiting_confirmation = State()


@dataclass
class PendingCosts:
    """Данные для отложенного сохранения."""

    valid_costs: list[Cost]
    invalid_lines: list[str]


def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру подтверждения."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, записать", callback_data=CALLBACK_CONFIRM_SAVE),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data=CALLBACK_CANCEL_SAVE),
        ]
    ])


def build_disable_past_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопкой 'Отключить прошлое'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹️ Отключить прошлое", callback_data=CALLBACK_DISABLE_PAST)]
    ])


def format_confirmation_message(valid_costs: list[Cost], invalid_lines: list[str]) -> str:
    """Форматирует сообщение с запросом подтверждения."""
    lines = ["⚠️ *Не удалось распознать строки:*", ""]

    for line in invalid_lines:
        lines.append(f"  • {line}")

    lines.append("")
    lines.append("*Будут записаны:*")
    lines.append("")

    for cost in valid_costs:
        lines.append(f"  • {cost.name}: {cost.amount}")

    lines.append("")
    count = len(valid_costs)
    word = pluralize(count, "расход", "расхода", "расходов")
    lines.append(f"Записать {count} {word}?")

    return "\n".join(lines)


async def save_costs_to_db(
    user_id: int,
    costs: list[Cost],
    created_at: datetime | None = None,
) -> bool:
    """Сохраняет расходы в БД. Возвращает True при успехе.
    
    Args:
        user_id: ID пользователя Telegram
        costs: список расходов
        created_at: опциональная дата создания (для режима ввода в прошлое)
    """
    async with get_session() as session:
        try:
            for cost in costs:
                text = f"{cost.name} {cost.amount}"
                await save_message(
                    session=session,
                    user_id=user_id,
                    text=text,
                    created_at=created_at,
                )
            await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.exception(
                "Database error while saving costs: user_id=%s, error=%s",
                user_id,
                type(e).__name__,
            )
            await session.rollback()
            return False


def get_past_mode_date(state_data: dict) -> datetime | None:
    """Получает дату из режима ввода в прошлое (1-е число месяца)."""
    year = state_data.get("past_mode_year")
    month = state_data.get("past_mode_month")
    
    if year is not None and month is not None:
        return datetime(year, month, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    return None


def format_past_mode_info(year: int, month: int) -> str:
    """Форматирует информацию о режиме ввода в прошлое."""
    month_name = MONTH_NAMES[month]
    return f"\n\n📅 _Записано на {month_name} {year}_"


@router.message(~Command(commands=["start", "help", "menu"]))
async def handle_message(message: Message, state: FSMContext):
    """Обработчик входящих сообщений с расходами."""
    if not message.text or not message.from_user:
        return

    result = parse_message(message.text)
    if result is None:
        logger.warning("Failed to parse message: user_id=%s, text=%r", message.from_user.id, message.text)
        await message.answer(MSG_PARSE_ERROR)
        await message.answer(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)
        return

    # Получаем данные о режиме ввода в прошлое
    state_data = await state.get_data()
    past_mode_date = get_past_mode_date(state_data)
    past_mode_year = state_data.get("past_mode_year")
    past_mode_month = state_data.get("past_mode_month")

    # Если есть невалидные строки - запрашиваем подтверждение
    if result.invalid_lines:
        logger.info(
            "Partial parse, asking confirmation: user_id=%s, valid=%d, invalid=%d",
            message.from_user.id,
            len(result.valid_lines),
            len(result.invalid_lines),
        )

        # Сохраняем данные в FSM (сохраняем past_mode_*)
        await state.set_state(SaveCostsStates.waiting_confirmation)
        await state.update_data(
            valid_costs=[{"name": c.name, "amount": str(c.amount)} for c in result.valid_lines],
            invalid_lines=result.invalid_lines,
        )

        confirmation_msg = format_confirmation_message(result.valid_lines, result.invalid_lines)
        keyboard = build_confirmation_keyboard()

        await message.answer(confirmation_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return

    # Все строки валидные - сохраняем сразу
    success = await save_costs_to_db(
        message.from_user.id,
        result.valid_lines,
        created_at=past_mode_date,
    )

    if success:
        count = len(result.valid_lines)
        logger.info("Successfully saved %d costs: user_id=%s", count, message.from_user.id)
        word = pluralize(count, "расход", "расхода", "расходов")
        
        response_text = MSG_SUCCESS.format(count=count, word=word)
        
        # Если активен режим ввода в прошлое - добавляем информацию и кнопку
        if past_mode_year and past_mode_month:
            response_text += format_past_mode_info(past_mode_year, past_mode_month)
            keyboard = build_disable_past_keyboard()
            await message.answer(response_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        else:
            await message.answer(response_text)
    else:
        await message.answer(MSG_DB_ERROR)


@router.callback_query(F.data == CALLBACK_CONFIRM_SAVE, SaveCostsStates.waiting_confirmation)
async def handle_confirm_save(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения сохранения."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    data = await state.get_data()
    valid_costs_data = data.get("valid_costs", [])

    if not valid_costs_data:
        await callback.answer("Нет данных для сохранения")
        await state.clear()
        return

    # Получаем данные о режиме ввода в прошлое
    past_mode_date = get_past_mode_date(data)
    past_mode_year = data.get("past_mode_year")
    past_mode_month = data.get("past_mode_month")

    # Восстанавливаем объекты Cost
    from decimal import Decimal
    valid_costs = [Cost(name=c["name"], amount=Decimal(c["amount"])) for c in valid_costs_data]

    # Сохраняем в БД
    success = await save_costs_to_db(
        callback.from_user.id,
        valid_costs,
        created_at=past_mode_date,
    )

    # Очищаем только состояние подтверждения, сохраняем past_mode_*
    await state.set_state(None)
    await state.update_data(valid_costs=None, invalid_lines=None)

    if success:
        count = len(valid_costs)
        logger.info("User %s confirmed saving %d costs", callback.from_user.id, count)
        word = pluralize(count, "расход", "расхода", "расходов")
        
        response_text = f"✅ {MSG_SUCCESS.format(count=count, word=word)}"
        
        # Если активен режим ввода в прошлое - добавляем информацию и кнопку
        if past_mode_year and past_mode_month:
            response_text += format_past_mode_info(past_mode_year, past_mode_month)
            keyboard = build_disable_past_keyboard()
            await callback.answer()
            await callback.message.edit_text(response_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await callback.answer()
            await callback.message.edit_text(response_text, reply_markup=None)
    else:
        await callback.answer()
        await callback.message.edit_text(MSG_DB_ERROR, reply_markup=None)


@router.callback_query(F.data == CALLBACK_CANCEL_SAVE, SaveCostsStates.waiting_confirmation)
async def handle_cancel_save(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены сохранения."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    logger.info("User %s cancelled saving costs", callback.from_user.id)

    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "❌ Сохранение отменено. Исправьте ошибки и отправьте сообщение снова.",
        reply_markup=None,
    )
