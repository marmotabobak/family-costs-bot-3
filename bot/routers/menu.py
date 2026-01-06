"""Роутер для команды /menu и обработки inline-кнопок."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.dependencies import get_session
from bot.db.repositories.messages import get_unique_user_ids

logger = logging.getLogger(__name__)
router = Router()

# Префиксы для callback_data
CALLBACK_MY_COSTS = "my_costs"
CALLBACK_USER_COSTS_PREFIX = "user_costs:"


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
    """Обработчик кнопки 'Мои расходы' (заглушка)."""
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    logger.info("User %s requested their costs", callback.from_user.id)

    await callback.answer()  # Убираем "часики" на кнопке
    await callback.message.answer(
        f"🚧 Функция 'Мои расходы' в разработке.\n"
        f"User ID: {callback.from_user.id}"
    )


@router.callback_query(F.data.startswith(CALLBACK_USER_COSTS_PREFIX))
async def handle_user_costs(callback: CallbackQuery):
    """Обработчик кнопки 'Расходы <user_id>' (заглушка)."""
    if not callback.data or not callback.from_user or not isinstance(callback.message, Message):
        return

    target_user_id = callback.data.removeprefix(CALLBACK_USER_COSTS_PREFIX)

    logger.info(
        "User %s requested costs for user %s",
        callback.from_user.id,
        target_user_id,
    )

    await callback.answer()  # Убираем "часики" на кнопке
    await callback.message.answer(
        f"🚧 Функция 'Расходы пользователя' в разработке.\n"
        f"Запрошены расходы пользователя: {target_user_id}"
    )
