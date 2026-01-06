"""Middleware для aiogram."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.config import settings
from bot.constants import MSG_ACCESS_DENIED

logger = logging.getLogger(__name__)


class AllowedUsersMiddleware(BaseMiddleware):
    """Middleware для проверки доступа пользователей по telegram user_id."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Если список разрешённых пользователей пуст - пропускаем всех
        if not settings.allowed_user_ids:
            return await handler(event, data)

        # Проверяем только сообщения
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        if user.id not in settings.allowed_user_ids:
            logger.warning(
                "Access denied for user: user_id=%s, username=%s",
                user.id,
                user.username,
            )
            await event.answer(MSG_ACCESS_DENIED)
            return None

        return await handler(event, data)
