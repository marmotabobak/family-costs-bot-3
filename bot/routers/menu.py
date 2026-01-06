"""Роутер для команды /menu и обработки inline-кнопок."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import (
    UserCostsStats,
    get_unique_user_ids,
    get_user_costs_stats,
    get_user_recent_costs,
)

logger = logging.getLogger(__name__)
router = Router()

# Префиксы для callback_data
CALLBACK_MY_COSTS = "my_costs"
CALLBACK_USER_COSTS_PREFIX = "user_costs:"


def format_costs_report(stats: UserCostsStats, recent_costs: list, user_id: int, is_own: bool = True) -> str:
    """Форматирует отчёт о расходах пользователя."""
    if stats.count == 0:
        if is_own:
            return "📭 У вас пока нет записанных расходов."
        return f"📭 У пользователя {user_id} пока нет записанных расходов."

    header = "📊 *Ваши расходы*" if is_own else f"📊 *Расходы пользователя {user_id}*"

    lines = [
        header,
        "",
        f"💰 *Всего:* {stats.total_amount:.2f}",
        f"📝 *Записей:* {stats.count}",
    ]

    if stats.first_date and stats.last_date:
        lines.append(f"📅 *Период:* {stats.first_date.strftime('%d.%m.%Y')} — {stats.last_date.strftime('%d.%m.%Y')}")

    if recent_costs:
        lines.append("")
        lines.append("🕐 *Последние записи:*")
        for name, amount, date in recent_costs:
            date_str = date.strftime("%d.%m")
            lines.append(f"  • {name}: {amount:.2f} ({date_str})")

    return "\n".join(lines)


def build_menu_keyboard(current_user_id: int, all_user_ids: list[int]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру меню с кнопками расходов."""
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


@router.message(Command("menu"))
async def menu_command(message: Message):
    """Обработчик команды /menu - показывает меню с кнопками."""
    if not message.from_user:
        return

    async with get_session() as session:
        user_ids = await get_unique_user_ids(session)

    keyboard = build_menu_keyboard(message.from_user.id, user_ids)

    await message.answer("📋 Меню:", reply_markup=keyboard)


@router.callback_query(F.data == CALLBACK_MY_COSTS)
async def handle_my_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Мои расходы'."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    user_id = callback.from_user.id
    logger.info("User %s requested their costs", user_id)

    async with get_session() as session:
        stats = await get_user_costs_stats(session, user_id)
        recent_costs = await get_user_recent_costs(session, user_id, limit=5)

    report = format_costs_report(stats, recent_costs, user_id, is_own=True)

    await callback.answer()
    await callback.message.answer(report, parse_mode="Markdown")


@router.callback_query(F.data.startswith(CALLBACK_USER_COSTS_PREFIX))
async def handle_user_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Расходы <user_id>'."""
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
        "User %s requested costs for user %s",
        callback.from_user.id,
        target_user_id,
    )

    async with get_session() as session:
        stats = await get_user_costs_stats(session, target_user_id)
        recent_costs = await get_user_recent_costs(session, target_user_id, limit=5)

    report = format_costs_report(stats, recent_costs, target_user_id, is_own=False)

    await callback.answer()
    await callback.message.answer(report, parse_mode="Markdown")
