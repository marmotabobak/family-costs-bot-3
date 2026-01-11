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

from bot.constants import (
    HELP_TEXT,
    MSG_DB_ERROR,
    MSG_PARSE_ERROR,
    MSG_MESSAGE_MAX_LENGTH,
    MSG_MESSAGE_MAX_LINES_COUNT,
    MSG_MESSAGE_MAX_LINE_LENGTH,
)
from bot.db.dependencies import get_session
from bot.db.repositories.messages import delete_messages_by_ids, save_message
from bot.services.message_parser import Cost, parse_message
from bot.utils import pluralize
from bot.exceptions import MessageMaxLinesCountExceed, MessageMaxLengthExceed, MessageMaxLineLengthExceed

# Названия месяцев (дублируем из menu.py для независимости)
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

logger = logging.getLogger(__name__)
router = Router()

# Callback data для подтверждения
CALLBACK_CONFIRM_PREFIX = "confirm:"  # confirm:<session_id>
CALLBACK_CANCEL_PREFIX = "cancel:"    # cancel:<session_id>
CALLBACK_DISABLE_PAST = "disable_past"  # отключить режим ввода в прошлое
CALLBACK_UNDO_PREFIX = "undo:"  # отменить запись: undo:<ids>


class SaveCostsStates(StatesGroup):
    """Состояния FSM для сохранения расходов."""

    waiting_confirmation = State()


@dataclass
class PendingCosts:
    """Данные для отложенного сохранения."""

    valid_costs: list[Cost]
    invalid_lines: list[str]


def generate_session_id() -> str:
    """Генерирует уникальный идентификатор сессии подтверждения."""
    import time
    return str(int(time.time() * 1000))  # timestamp в миллисекундах


def build_confirmation_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру подтверждения с уникальным session_id."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, записать",
                callback_data=f"{CALLBACK_CONFIRM_PREFIX}{session_id}",
            ),
            InlineKeyboardButton(
                text="❌ Нет, отменить",
                callback_data=f"{CALLBACK_CANCEL_PREFIX}{session_id}",
            ),
        ]
    ])


def build_disable_past_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопкой 'Отключить прошлое'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹️ Отключить прошлое", callback_data=CALLBACK_DISABLE_PAST)]
    ])


def build_success_keyboard(
    message_ids: list[int],
    include_disable_past: bool = False,
) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопкой отмены (и опционально 'Отключить прошлое').
    
    Args:
        message_ids: ID сохранённых записей для возможности отмены
        include_disable_past: добавить кнопку 'Отключить прошлое'
    """
    # Формируем callback_data: undo:1,2,3
    ids_str = ",".join(str(id) for id in message_ids)
    undo_callback = f"{CALLBACK_UNDO_PREFIX}{ids_str}"
    
    buttons = [[InlineKeyboardButton(text="↩️ Отменить", callback_data=undo_callback)]]
    
    if include_disable_past:
        buttons.append([
            InlineKeyboardButton(text="⏹️ Отключить прошлое", callback_data=CALLBACK_DISABLE_PAST)
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_success_message(costs: list[Cost], count: int) -> str:
    """Форматирует сообщение об успешной записи со списком расходов.
    
    Args:
        costs: список записанных расходов
        count: количество записей
    
    Returns:
        Форматированное сообщение
    """
    word = pluralize(count, "расход", "расхода", "расходов")
    
    lines = [f"✅ Записано {count} {word}:", ""]
    for cost in costs:
        lines.append(f"  • {cost.name}: {cost.amount}")
    
    return "\n".join(lines)


def format_confirmation_message(valid_costs: list[Cost], invalid_lines: list[str]) -> str:
    """Форматирует сообщение с запросом подтверждения."""
    lines = ["⚠️ *Не удалось распознать строки:*", ""]  # TODO: Вынести в константы

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
) -> list[int] | None:
    """Сохраняет расходы в БД. Возвращает список ID сохранённых записей или None при ошибке.
    
    Args:
        user_id: ID пользователя Telegram
        costs: список расходов
        created_at: опциональная дата создания (для режима ввода в прошлое)
    
    Returns:
        Список ID сохранённых записей или None при ошибке
    """
    async with get_session() as session:
        try:
            saved_ids: list[int] = []
            for cost in costs:
                text = f"{cost.name} {cost.amount}"
                message = await save_message(
                    session=session,
                    user_id=user_id,
                    text=text,
                    created_at=created_at,
                )
                saved_ids.append(int(message.id))
            await session.commit()
            return saved_ids
        except SQLAlchemyError as e:
            logger.exception(
                "Database error while saving costs: user_id=%s, error=%s",
                user_id,
                type(e).__name__,
            )
            await session.rollback()
            return None


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

    if result is None:
        logger.warning("Failed to parse message: user_id=%s, text=%r", message.from_user.id, message.text)
        await message.answer(MSG_PARSE_ERROR)
        await message.answer(HELP_TEXT)
        return

    # Получаем данные о режиме ввода в прошлое
    state_data = await state.get_data()
    past_mode_date = get_past_mode_date(state_data)
    past_mode_year = state_data.get("past_mode_year")
    past_mode_month = state_data.get("past_mode_month")

    # Если есть невалидные строки - запрашиваем подтверждение
    if result.invalid_lines:
        session_id = generate_session_id()
        logger.info(
            "Partial parse, asking confirmation: user_id=%s, valid=%d, invalid=%d, session=%s",
            message.from_user.id,
            len(result.valid_lines),
            len(result.invalid_lines),
            session_id,
        )

        # Сохраняем данные в FSM (сохраняем past_mode_*) + session_id
        await state.set_state(SaveCostsStates.waiting_confirmation)
        await state.update_data(
            valid_costs=[{"name": c.name, "amount": str(c.amount)} for c in result.valid_lines],
            invalid_lines=result.invalid_lines,
            confirmation_session_id=session_id,
        )

        confirmation_msg = format_confirmation_message(result.valid_lines, result.invalid_lines)
        keyboard = build_confirmation_keyboard(session_id)

        await message.answer(confirmation_msg, reply_markup=keyboard)
        return

    # Все строки валидные - сохраняем сразу
    saved_ids = await save_costs_to_db(
        message.from_user.id,
        result.valid_lines,
        created_at=past_mode_date,
    )

    if saved_ids is not None:
        count = len(result.valid_lines)
        logger.info("Successfully saved %d costs: user_id=%s, ids=%s", count, message.from_user.id, saved_ids)
        
        response_text = format_success_message(result.valid_lines, count)
        
        # Если активен режим ввода в прошлое - добавляем информацию
        if past_mode_year and past_mode_month:
            response_text += format_past_mode_info(past_mode_year, past_mode_month)
        
        keyboard = build_success_keyboard(
            saved_ids,
            include_disable_past=bool(past_mode_year and past_mode_month),
        )

        await message.answer(response_text, reply_markup=keyboard)
    else:
        await message.answer(MSG_DB_ERROR)


@router.callback_query(F.data.startswith(CALLBACK_CONFIRM_PREFIX), SaveCostsStates.waiting_confirmation)
async def handle_confirm_save(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения сохранения."""
    if not callback.from_user or not isinstance(callback.message, Message) or not callback.data:
        return

    # Проверяем session_id
    callback_session_id = callback.data.removeprefix(CALLBACK_CONFIRM_PREFIX)
    data = await state.get_data()
    stored_session_id = data.get("confirmation_session_id")

    if callback_session_id != stored_session_id:
        logger.warning(
            "Session mismatch: callback=%s, stored=%s, user=%s",
            callback_session_id,
            stored_session_id,
            callback.from_user.id,
        )
        await callback.answer("⚠️ Это сообщение устарело. Используйте последнее.", show_alert=True)
        return

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
    saved_ids = await save_costs_to_db(
        callback.from_user.id,
        valid_costs,
        created_at=past_mode_date,
    )

    # Очищаем только состояние подтверждения, сохраняем past_mode_*
    await state.set_state(None)
    await state.update_data(valid_costs=None, invalid_lines=None, confirmation_session_id=None)

    if saved_ids is not None:
        count = len(valid_costs)
        logger.info("User %s confirmed saving %d costs, ids=%s", callback.from_user.id, count, saved_ids)
        
        response_text = format_success_message(valid_costs, count)
        
        # Если активен режим ввода в прошлое - добавляем информацию
        if past_mode_year and past_mode_month:
            response_text += format_past_mode_info(past_mode_year, past_mode_month)
        
        keyboard = build_success_keyboard(
            saved_ids,
            include_disable_past=bool(past_mode_year and past_mode_month),
        )
        await callback.answer()
        await callback.message.edit_text(response_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await callback.answer()
        await callback.message.edit_text(MSG_DB_ERROR, reply_markup=None)


@router.callback_query(F.data.startswith(CALLBACK_CANCEL_PREFIX), SaveCostsStates.waiting_confirmation)
async def handle_cancel_save(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены сохранения."""
    if not callback.from_user or not isinstance(callback.message, Message) or not callback.data:
        return

    # Проверяем session_id
    callback_session_id = callback.data.removeprefix(CALLBACK_CANCEL_PREFIX)
    data = await state.get_data()
    stored_session_id = data.get("confirmation_session_id")

    if callback_session_id != stored_session_id:
        logger.warning(
            "Session mismatch on cancel: callback=%s, stored=%s, user=%s",
            callback_session_id,
            stored_session_id,
            callback.from_user.id,
        )
        await callback.answer("⚠️ Это сообщение устарело. Используйте последнее.", show_alert=True)
        return

    logger.info("User %s cancelled saving costs", callback.from_user.id)

    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "❌ Сохранение отменено. Исправьте ошибки и отправьте сообщение снова.",
        reply_markup=None,
    )


@router.callback_query(F.data.startswith(CALLBACK_UNDO_PREFIX))
async def handle_undo(callback: CallbackQuery):
    """Обработчик отмены записанных расходов."""
    if not callback.from_user or not isinstance(callback.message, Message) or not callback.data:
        return

    # Парсим ID из callback_data: undo:1,2,3
    ids_str = callback.data.removeprefix(CALLBACK_UNDO_PREFIX)
    try:
        message_ids = [int(id_str) for id_str in ids_str.split(",") if id_str]
    except ValueError:
        logger.error("Invalid undo callback data: %s", callback.data)
        await callback.answer("Ошибка: некорректные данные", show_alert=True)
        return

    if not message_ids:
        await callback.answer("Нет записей для удаления", show_alert=True)
        return

    user_id = callback.from_user.id
    
    async with get_session() as session:
        try:
            deleted_count = await delete_messages_by_ids(session, message_ids, user_id)
            await session.commit()
            
            logger.info(
                "User %s undid %d costs (requested %d)",
                user_id,
                deleted_count,
                len(message_ids),
            )
            
            word = pluralize(deleted_count, "запись", "записи", "записей")
            await callback.answer()
            await callback.message.edit_text(
                f"↩️ Отменено: удалено {deleted_count} {word}.",
                reply_markup=None,
            )
        except SQLAlchemyError as e:
            logger.exception(
                "Database error while undoing costs: user_id=%s, error=%s",
                user_id,
                type(e).__name__,
            )
            await session.rollback()
            await callback.answer("Ошибка при удалении", show_alert=True)
