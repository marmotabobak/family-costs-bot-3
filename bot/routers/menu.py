"""Роутер для команды /menu и обработки inline-кнопок."""

import logging
from datetime import datetime
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import (
    get_unique_user_ids,
    get_user_costs_by_month,
)

logger = logging.getLogger(__name__)
router = Router()

# Callback prefixes
CALLBACK_MY_COSTS = "my_costs"
CALLBACK_USER_COSTS_PREFIX = "user_costs:"
CALLBACK_PERIOD_PREFIX = "period:"  # period:<user_id>:<period_type>
CALLBACK_MONTH_PREFIX = "month:"    # month:<user_id>:<year>:<month>
CALLBACK_ENTER_PAST = "enter_past"  # начать ввод за прошлый месяц
CALLBACK_ENTER_PAST_YEAR = "enter_past_year:"  # выбор года для ввода
CALLBACK_ENTER_PAST_MONTH = "enter_past_month:"  # выбор месяца для ввода
CALLBACK_DISABLE_PAST = "disable_past"  # отключить режим ввода в прошлое

# Названия месяцев
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def build_menu_keyboard(current_user_id: int, all_user_ids: list[int]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру главного меню с кнопками расходов."""
    buttons = []

    # Кнопка "Мои расходы"
    buttons.append([InlineKeyboardButton(text="📊 Мои расходы", callback_data=CALLBACK_MY_COSTS)])

    # Кнопки для каждого пользователя из базы
    for user_id in all_user_ids:
        if user_id == current_user_id:
            continue  # Пропускаем текущего пользователя (у него есть "Мои расходы")
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 Расходы {user_id}",
                callback_data=f"{CALLBACK_USER_COSTS_PREFIX}{user_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_period_keyboard(user_id: int, is_own: bool) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора периода."""
    prefix = f"{CALLBACK_PERIOD_PREFIX}{user_id}:"
    
    buttons = [
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data=f"{prefix}this_month")],
        [InlineKeyboardButton(text="📅 Прошлый месяц", callback_data=f"{prefix}prev_month")],
        [InlineKeyboardButton(text="📅 Другие месяцы", callback_data=f"{prefix}other")],
    ]
    
    # Кнопка "Внести расходы за другой месяц" только для своих расходов
    if is_own:
        buttons.append([
            InlineKeyboardButton(
                text="✏️ Внести расходы за другой месяц",
                callback_data=CALLBACK_ENTER_PAST,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_months_keyboard(user_id: int, available_months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком доступных месяцев."""
    buttons = []
    
    for year, month in available_months:
        month_name = f"{MONTH_NAMES[month]} {year}"
        callback_data = f"{CALLBACK_MONTH_PREFIX}{user_id}:{year}:{month}"
        buttons.append([InlineKeyboardButton(text=month_name, callback_data=callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_month_report(
    costs: list[tuple[str, Decimal, datetime]],
    year: int,
    month: int,
    user_id: int,
    is_own: bool,
) -> str:
    """Форматирует отчёт по расходам за месяц."""
    month_name = MONTH_NAMES[month]
    header = f"*{month_name} {year}*"
    
    if not costs:
        if is_own:
            return f"{header}\n\n📭 Нет расходов за этот период."
        return f"{header}\n\n📭 У пользователя {user_id} нет расходов за этот период."

    total = sum(amount for _, amount, _ in costs)
    
    lines = [header, "", f"*Всего:* {total:.2f}", ""]
    
    # Сортируем по дате по возрастанию (costs уже отсортированы в репозитории)
    for name, amount, date in costs:
        date_str = date.strftime("%d.%m")
        lines.append(f"{date_str} {name} {amount:.2f}")

    return "\n".join(lines)


@router.message(Command("menu"))
async def menu_command(message: Message):
    """Обработчик команды /menu - показывает меню с кнопками."""
    if not message.from_user:
        return

    async with get_session() as session:
        user_ids = await get_unique_user_ids(session)

    keyboard = build_menu_keyboard(message.from_user.id, user_ids)

    await message.answer("📋 Расходы:", reply_markup=keyboard)


@router.callback_query(F.data == CALLBACK_MY_COSTS)
async def handle_my_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Мои расходы' - показывает выбор периода."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    user_id = callback.from_user.id
    logger.info("User %s opened period selection for their costs", user_id)

    keyboard = build_period_keyboard(user_id, is_own=True)

    await callback.answer()
    await callback.message.answer("📊 Мои расходы", reply_markup=keyboard)


@router.callback_query(F.data.startswith(CALLBACK_USER_COSTS_PREFIX))
async def handle_user_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Расходы <user_id>' - показывает выбор периода."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    target_user_id_str = callback.data.removeprefix(CALLBACK_USER_COSTS_PREFIX)

    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        logger.warning("Invalid user_id in callback: %s", target_user_id_str)
        await callback.answer("Ошибка: некорректный ID пользователя")
        return

    logger.info(
        "User %s opened period selection for user %s",
        callback.from_user.id,
        target_user_id,
    )

    keyboard = build_period_keyboard(target_user_id, is_own=False)

    await callback.answer()
    await callback.message.answer(
        f"📊 Расходы пользователя {target_user_id}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith(CALLBACK_PERIOD_PREFIX))
async def handle_period_selection(callback: CallbackQuery):
    """Обработчик выбора периода."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    # Парсим callback_data: period:<user_id>:<period_type>
    parts = callback.data.removeprefix(CALLBACK_PERIOD_PREFIX).split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка")
        return

    try:
        target_user_id = int(parts[0])
    except ValueError:
        await callback.answer("Ошибка")
        return

    period_type = parts[1]
    is_own = target_user_id == callback.from_user.id
    now = datetime.now()

    if period_type == "this_month":
        year, month = now.year, now.month
        await _show_month_report(callback, target_user_id, year, month, is_own)

    elif period_type == "prev_month":
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        await _show_month_report(callback, target_user_id, year, month, is_own)

    elif period_type == "other":
        await _show_months_list(callback, target_user_id, is_own)

    else:
        await callback.answer("Неизвестный период")


@router.callback_query(F.data.startswith(CALLBACK_MONTH_PREFIX))
async def handle_month_selection(callback: CallbackQuery):
    """Обработчик выбора конкретного месяца."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    # Парсим callback_data: month:<user_id>:<year>:<month>
    parts = callback.data.removeprefix(CALLBACK_MONTH_PREFIX).split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка")
        return

    try:
        target_user_id = int(parts[0])
        year = int(parts[1])
        month = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка")
        return

    is_own = target_user_id == callback.from_user.id
    await _show_month_report(callback, target_user_id, year, month, is_own)


async def _show_month_report(
    callback: CallbackQuery,
    user_id: int,
    year: int,
    month: int,
    is_own: bool,
) -> None:
    """Показывает отчёт за конкретный месяц."""
    if not isinstance(callback.message, Message):
        return

    async with get_session() as session:
        costs = await get_user_costs_by_month(session, user_id, year, month)

    report = format_month_report(costs, year, month, user_id, is_own)

    await callback.answer()
    await callback.message.answer(report, parse_mode="Markdown")


async def _show_months_list(callback: CallbackQuery, user_id: int, is_own: bool) -> None:
    """Показывает список доступных месяцев."""
    if not isinstance(callback.message, Message):
        return

    from bot.db.repositories.messages import get_user_available_months

    async with get_session() as session:
        months = await get_user_available_months(session, user_id)

    if not months:
        await callback.answer()
        msg = "📭 Нет данных о расходах." if is_own else f"📭 У пользователя {user_id} нет данных о расходах."
        await callback.message.answer(msg)
        return

    keyboard = build_months_keyboard(user_id, months)
    
    title = "📊 Мои расходы" if is_own else f"📊 Расходы пользователя {user_id}"
    
    await callback.answer()
    await callback.message.answer(title, reply_markup=keyboard)


# ============== Ввод расходов за другой месяц ==============

def build_past_years_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора года (текущий и предыдущий)."""
    now = datetime.now()
    current_year = now.year
    
    buttons = [
        [InlineKeyboardButton(
            text=str(current_year),
            callback_data=f"{CALLBACK_ENTER_PAST_YEAR}{current_year}",
        )],
        [InlineKeyboardButton(
            text=str(current_year - 1),
            callback_data=f"{CALLBACK_ENTER_PAST_YEAR}{current_year - 1}",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_past_months_keyboard(year: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для выбора месяца (только прошлые месяцы)."""
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    buttons = []
    
    # Для выбранного года показываем только прошлые месяцы
    if year < current_year:
        # Прошлый год - показываем все 12 месяцев
        months_to_show = range(1, 13)
    else:
        # Текущий год - только прошлые месяцы (до текущего)
        months_to_show = range(1, current_month)
    
    # Группируем по 3 кнопки в ряд
    row = []
    for month in months_to_show:
        row.append(InlineKeyboardButton(
            text=MONTH_NAMES[month][:3],  # Янв, Фев, Мар...
            callback_data=f"{CALLBACK_ENTER_PAST_MONTH}{year}:{month}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    
    if row:  # Оставшиеся кнопки
        buttons.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_disable_past_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопкой 'Отключить прошлое'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹️ Отключить прошлое", callback_data=CALLBACK_DISABLE_PAST)]
    ])


@router.callback_query(F.data == CALLBACK_ENTER_PAST)
async def handle_enter_past(callback: CallbackQuery):
    """Обработчик кнопки 'Внести расходы за другой месяц' - показывает выбор года."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    logger.info("User %s started entering past costs", callback.from_user.id)

    keyboard = build_past_years_keyboard()

    await callback.answer()
    await callback.message.answer("📅 Выберите год:", reply_markup=keyboard)


@router.callback_query(F.data.startswith(CALLBACK_ENTER_PAST_YEAR))
async def handle_enter_past_year(callback: CallbackQuery):
    """Обработчик выбора года для ввода расходов в прошлое."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    year_str = callback.data.removeprefix(CALLBACK_ENTER_PAST_YEAR)

    try:
        year = int(year_str)
    except ValueError:
        await callback.answer("Ошибка")
        return

    logger.info("User %s selected year %d for past costs", callback.from_user.id, year)

    keyboard = build_past_months_keyboard(year)

    # Проверяем, есть ли доступные месяцы
    if not keyboard.inline_keyboard:
        await callback.answer("Нет доступных прошлых месяцев для этого года", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(f"📅 Выберите месяц ({year}):", reply_markup=keyboard)


@router.callback_query(F.data.startswith(CALLBACK_ENTER_PAST_MONTH))
async def handle_enter_past_month(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора месяца для ввода расходов в прошлое - включает режим."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    # Парсим year:month
    parts = callback.data.removeprefix(CALLBACK_ENTER_PAST_MONTH).split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка")
        return

    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        await callback.answer("Ошибка")
        return

    logger.info(
        "User %s enabled past mode for %s %d",
        callback.from_user.id,
        MONTH_NAMES[month],
        year,
    )

    # Сохраняем режим в FSM
    await state.update_data(past_mode_year=year, past_mode_month=month)

    month_name = MONTH_NAMES[month]
    keyboard = build_disable_past_keyboard()

    await callback.answer()
    await callback.message.answer(
        f"⚠️ *Внимание!*\n\n"
        f"Все последующие расходы будут внесены на 1-е число месяца: *{month_name} {year}*.\n\n"
        f"Когда захотите отключить режим ввода за прошлые месяца, нажмите кнопку ниже, "
        f"чтобы новые расходы были записаны по умолчанию — на сегодня.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == CALLBACK_DISABLE_PAST)
async def handle_disable_past(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Отключить прошлое' - выключает режим."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    # Очищаем режим из FSM
    data = await state.get_data()
    
    # Удаляем только past_mode_*, оставляя остальные данные
    if "past_mode_year" in data or "past_mode_month" in data:
        data.pop("past_mode_year", None)
        data.pop("past_mode_month", None)
        await state.set_data(data)

    logger.info("User %s disabled past mode", callback.from_user.id)

    await callback.answer()
    await callback.message.edit_text(
        "✅ Прошлое ушло. Дальнейшие расходы будут занесены на сегодня.",
        reply_markup=None,
    )
