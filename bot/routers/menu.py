"""Роутер для команды /menu и обработки inline-кнопок."""

import logging
from datetime import datetime
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import (
    get_all_users_costs_by_month,
    get_available_months,
    get_unique_user_ids,
    get_user_costs_by_month,
)
from bot.db.repositories.users import get_all_users, get_user_by_telegram_id
from bot.utils import format_amount

logger = logging.getLogger(__name__)
router = Router()

# Callback prefixes
CALLBACK_MY_COSTS = "my_costs"
CALLBACK_USER_COSTS_PREFIX = "user_costs:"
CALLBACK_PERIOD_PREFIX = "period:"  # period:<user_id>:<period_type>
CALLBACK_MONTH_PREFIX = "month:"    # month:<user_id>:<year>:<month>
CALLBACK_SUMMARY = "summary"
CALLBACK_SUMMARY_PERIOD_PREFIX = "sum_period:"  # sum_period:<period_type>
CALLBACK_SUMMARY_MONTH_PREFIX = "sum_month:"    # sum_month:<year>:<month>

# Названия месяцев
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def build_menu_keyboard(current_user_id: int, user_names: dict[int, str]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру главного меню с кнопками расходов."""
    buttons = []

    # Кнопка "Мои расходы"
    buttons.append([InlineKeyboardButton(text="📊 Мои расходы", callback_data=CALLBACK_MY_COSTS)])

    # Кнопки для каждого пользователя из базы
    for telegram_id, name in user_names.items():
        if telegram_id == current_user_id:
            continue  # Пропускаем текущего пользователя (у него есть "Мои расходы")
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 Расходы {name}",
                callback_data=f"{CALLBACK_USER_COSTS_PREFIX}{telegram_id}",
            )
        ])

    # Кнопка "Сводная" (сводный отчёт по всем пользователям)
    buttons.append([InlineKeyboardButton(text="📈 Сводная", callback_data=CALLBACK_SUMMARY)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_period_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора периода."""
    prefix = f"{CALLBACK_PERIOD_PREFIX}{user_id}:"

    buttons = [
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data=f"{prefix}this_month")],
        [InlineKeyboardButton(text="📅 Прошлый месяц", callback_data=f"{prefix}prev_month")],
        [InlineKeyboardButton(text="📅 Другие месяцы", callback_data=f"{prefix}other")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_months_keyboard(user_id: int, available_months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком доступных месяцев."""
    buttons = []

    for year, month in available_months:
        month_name = f"{MONTH_NAMES[month]} {year}"
        callback_data = f"{CALLBACK_MONTH_PREFIX}{user_id}:{year}:{month}"
        buttons.append([InlineKeyboardButton(text=month_name, callback_data=callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_summary_period_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора периода для сводного отчёта."""
    buttons = [
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data=f"{CALLBACK_SUMMARY_PERIOD_PREFIX}this_month")],
        [InlineKeyboardButton(text="📅 Прошлый месяц", callback_data=f"{CALLBACK_SUMMARY_PERIOD_PREFIX}prev_month")],
        [InlineKeyboardButton(text="📅 Другие месяцы", callback_data=f"{CALLBACK_SUMMARY_PERIOD_PREFIX}other")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_summary_months_keyboard(available_months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком доступных месяцев для сводного отчёта."""
    buttons = []

    for year, month in available_months:
        month_name = f"{MONTH_NAMES[month]} {year}"
        callback_data = f"{CALLBACK_SUMMARY_MONTH_PREFIX}{year}:{month}"
        buttons.append([InlineKeyboardButton(text=month_name, callback_data=callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_month_report(
    costs: list[tuple[str, Decimal, datetime]],
    year: int,
    month: int,
    user_name: str,
    is_own: bool,
) -> str:
    """Форматирует отчёт по расходам за месяц."""
    month_name = MONTH_NAMES[month]
    header = f"<b>{month_name} {year}</b>"

    if not costs:
        if is_own:
            return f"{header}\n\n📭 Нет расходов за этот период."
        return f"{header}\n\n📭 У пользователя {user_name} нет расходов за этот период."

    total = sum((amount for _, amount, _ in costs), Decimal(0))

    lines = [header, "", f"<b>Всего:</b> {format_amount(total, sep='_')}", ""]

    # Сортируем по дате по возрастанию (costs уже отсортированы в репозитории)
    for name, amount, date in costs:
        date_str = date.strftime("%d")
        lines.append(f"{date_str}: {name} {format_amount(amount, sep='_')}")

    return "\n".join(lines)


def format_summary_report(
    user_totals: dict[int, Decimal],
    user_names: dict[int, str],
    year: int,
    month: int,
) -> str:
    """Форматирует сводный отчёт по всем пользователям.

    Показывает:
    - Общую сумму расходов
    - Кто сколько должен заплатить для выравнивания
    - Расходы каждого пользователя
    """
    month_name = MONTH_NAMES[month]
    header = f"<b>{month_name} {year}</b>"

    if not user_totals:
        return f"{header}\n\n📭 Нет расходов за этот период."

    # Считаем общую сумму и среднее
    grand_total = sum(user_totals.values(), Decimal("0"))
    num_users = len(user_totals)
    fair_share = grand_total / num_users if num_users > 0 else Decimal("0")

    # Вычисляем разницу для каждого пользователя
    # Положительная разница = переплатил (ему должны)
    # Отрицательная разница = недоплатил (он должен)
    differences: dict[int, Decimal] = {}
    for uid, total in user_totals.items():
        differences[uid] = total - fair_share

    lines = [header, "", f"<b>Всего:</b> {format_amount(grand_total, sep='_')}", ""]

    # Кто должен заплатить (недоплатившие)
    debtors = [(uid, -diff) for uid, diff in differences.items() if diff < 0]
    if debtors:
        # Сортируем по сумме долга (больший долг сверху)
        debtors.sort(key=lambda x: x[1], reverse=True)
        for uid, debt in debtors:
            name = user_names.get(uid, str(uid))
            lines.append(f"<b>{name}:</b> надо заплатить {format_amount(debt, sep='_')}")
        lines.append("")

    # Расходы каждого пользователя (сортируем по сумме убывания)
    sorted_users = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)
    for uid, total in sorted_users:
        name = user_names.get(uid, str(uid))
        lines.append(f"{name}: {format_amount(total, sep='_')}")

    return "\n".join(lines)


@router.message(Command("menu"))
async def menu_command(message: Message):
    """Обработчик команды /menu - показывает меню с кнопками."""
    if not message.from_user:
        return

    async with get_session() as session:
        user_ids = await get_unique_user_ids(session)
        users = await get_all_users(session)

    users_map = {int(u.telegram_id): str(u.name) for u in users}
    user_names = {uid: users_map.get(uid, str(uid)) for uid in user_ids}

    keyboard = build_menu_keyboard(message.from_user.id, user_names)

    await message.answer("📋 Расходы:", reply_markup=keyboard)


@router.callback_query(F.data == CALLBACK_MY_COSTS)
async def handle_my_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Мои расходы' - показывает выбор периода."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    user_id = callback.from_user.id
    logger.info("User %s opened period selection for their costs", user_id)

    keyboard = build_period_keyboard(user_id)

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

    async with get_session() as session:
        user = await get_user_by_telegram_id(session, target_user_id)
    user_name = str(user.name) if user else str(target_user_id)

    keyboard = build_period_keyboard(target_user_id)

    await callback.answer()
    await callback.message.answer(
        f"📊 Расходы пользователя {user_name}",
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
        if not is_own:
            user = await get_user_by_telegram_id(session, user_id)
            user_name = str(user.name) if user else str(user_id)
        else:
            user_name = ""

    report = format_month_report(costs, year, month, user_name, is_own)

    await callback.answer()
    await callback.message.answer(report)


async def _show_months_list(callback: CallbackQuery, user_id: int, is_own: bool) -> None:
    """Показывает список доступных месяцев."""
    if not isinstance(callback.message, Message):
        return

    from bot.db.repositories.messages import get_user_available_months

    async with get_session() as session:
        months = await get_user_available_months(session, user_id)
        if not is_own:
            user = await get_user_by_telegram_id(session, user_id)
            user_name = str(user.name) if user else str(user_id)
        else:
            user_name = ""

    if not months:
        await callback.answer()
        msg = "📭 Нет данных о расходах." if is_own else f"📭 У пользователя {user_name} нет данных о расходах."
        await callback.message.answer(msg)
        return

    keyboard = build_months_keyboard(user_id, months)

    title = "📊 Мои расходы" if is_own else f"📊 Расходы пользователя {user_name}"

    await callback.answer()
    await callback.message.answer(title, reply_markup=keyboard)


# --- Сводный отчёт ---


@router.callback_query(F.data == CALLBACK_SUMMARY)
async def handle_summary(callback: CallbackQuery):
    """Обработчик кнопки 'Сводная' - показывает выбор периода."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    logger.info("User %s opened summary period selection", callback.from_user.id)

    keyboard = build_summary_period_keyboard()

    await callback.answer()
    await callback.message.answer("📈 Сводная", reply_markup=keyboard)


@router.callback_query(F.data.startswith(CALLBACK_SUMMARY_PERIOD_PREFIX))
async def handle_summary_period_selection(callback: CallbackQuery):
    """Обработчик выбора периода для сводного отчёта."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    period_type = callback.data.removeprefix(CALLBACK_SUMMARY_PERIOD_PREFIX)
    now = datetime.now()

    if period_type == "this_month":
        year, month = now.year, now.month
        await _show_summary_report(callback, year, month)

    elif period_type == "prev_month":
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        await _show_summary_report(callback, year, month)

    elif period_type == "other":
        await _show_summary_months_list(callback)

    else:
        await callback.answer("Неизвестный период")


@router.callback_query(F.data.startswith(CALLBACK_SUMMARY_MONTH_PREFIX))
async def handle_summary_month_selection(callback: CallbackQuery):
    """Обработчик выбора конкретного месяца для сводного отчёта."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    # Парсим callback_data: sum_month:<year>:<month>
    parts = callback.data.removeprefix(CALLBACK_SUMMARY_MONTH_PREFIX).split(":")
    if len(parts) != 2:
        await callback.answer("Ошибка")
        return

    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        await callback.answer("Ошибка")
        return

    await _show_summary_report(callback, year, month)


async def _show_summary_report(callback: CallbackQuery, year: int, month: int) -> None:
    """Показывает сводный отчёт за конкретный месяц."""
    if not isinstance(callback.message, Message):
        return

    async with get_session() as session:
        user_totals = await get_all_users_costs_by_month(session, year, month)
        users = await get_all_users(session)

    users_map = {int(u.telegram_id): str(u.name) for u in users}

    report = format_summary_report(user_totals, users_map, year, month)

    await callback.answer()
    await callback.message.answer(report)


async def _show_summary_months_list(callback: CallbackQuery) -> None:
    """Показывает список доступных месяцев для сводного отчёта."""
    if not isinstance(callback.message, Message):
        return

    async with get_session() as session:
        months = await get_available_months(session)

    if not months:
        await callback.answer()
        await callback.message.answer("📭 Нет данных о расходах.")
        return

    keyboard = build_summary_months_keyboard(months)

    await callback.answer()
    await callback.message.answer("📈 Сводная", reply_markup=keyboard)
