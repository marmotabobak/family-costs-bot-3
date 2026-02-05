"""Middleware для aiogram."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.constants import MSG_ACCESS_DENIED
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.users import get_all_telegram_ids

logger = logging.getLogger(__name__)


class AllowedUsersMiddleware(BaseMiddleware):
    """Middleware для проверки доступа пользователей по telegram user_id из базы данных."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Проверяем только сообщения
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        # Получаем список разрешённых пользователей из БД
        try:
            async with get_db_session() as session:
                allowed_ids = await get_all_telegram_ids(session)
        except Exception:
            logger.warning("Cannot access users table, allowing all users")
            return await handler(event, data)

        # Пустая таблица users — пропускаем всех
        if not allowed_ids:
            return await handler(event, data)

        if user.id not in allowed_ids:
            logger.warning(
                "Access denied for user: user_id=%s, username=%s",
                user.id,
                user.username,
            )
            await event.answer(MSG_ACCESS_DENIED)
            return None

        return await handler(event, data)
