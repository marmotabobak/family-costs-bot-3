"""Тесты middleware."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.middleware import AllowedUsersMiddleware


class TestAllowedUsersMiddleware:
    """Тесты AllowedUsersMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Фикстура middleware."""
        return AllowedUsersMiddleware()

    @pytest.fixture
    def handler(self):
        """Фикстура обработчика."""
        return AsyncMock(return_value="handler_result")

    @pytest.fixture
    def message_event(self):
        """Фикстура события Message."""
        from aiogram.types import Message, User

        user = MagicMock(spec=User)
        user.id = 123456
        user.username = "testuser"

        message = MagicMock(spec=Message)
        message.from_user = user
        message.answer = AsyncMock()

        return message

    def _mock_get_session(self, allowed_ids: list[int]):
        """Helper: creates a mock async context manager returning a session
        where get_all_telegram_ids returns allowed_ids."""

        @asynccontextmanager
        async def mock_ctx():
            yield AsyncMock()

        return mock_ctx

    @pytest.mark.asyncio
    async def test_allows_all_when_users_table_empty(self, middleware, handler, message_event):
        """Пропускает всех, если таблица users пуста."""
        with patch("bot.middleware.get_db_session") as mock_session_ctx, patch(
            "bot.middleware.get_all_telegram_ids", new=AsyncMock(return_value=[])
        ):
            mock_session_ctx.return_value = self._mock_get_session([])()

            result = await middleware(handler, message_event, {})

            handler.assert_called_once_with(message_event, {})
            assert result == "handler_result"
            message_event.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_user_in_list(self, middleware, handler, message_event):
        """Пропускает пользователя из списка разрешённых."""
        with patch("bot.middleware.get_db_session") as mock_session_ctx, patch(
            "bot.middleware.get_all_telegram_ids", new=AsyncMock(return_value=[123456, 789])
        ):
            mock_session_ctx.return_value = self._mock_get_session([123456, 789])()

            result = await middleware(handler, message_event, {})

            handler.assert_called_once_with(message_event, {})
            assert result == "handler_result"
            message_event.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_denies_user_not_in_list(self, middleware, handler, message_event):
        """Отклоняет пользователя не из списка."""
        with patch("bot.middleware.get_db_session") as mock_session_ctx, patch(
            "bot.middleware.get_all_telegram_ids", new=AsyncMock(return_value=[111, 222, 333])
        ):
            mock_session_ctx.return_value = self._mock_get_session([111, 222, 333])()

            result = await middleware(handler, message_event, {})

            handler.assert_not_called()
            assert result is None
            message_event.answer.assert_called_once()
            call_args = message_event.answer.call_args
            assert "🚫" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_passes_non_message_events(self, middleware, handler):
        """Пропускает события, не являющиеся Message."""
        from aiogram.types import CallbackQuery

        callback = MagicMock(spec=CallbackQuery)

        result = await middleware(handler, callback, {})

        handler.assert_called_once_with(callback, {})
        assert result == "handler_result"

    @pytest.mark.asyncio
    async def test_passes_message_without_user(self, middleware, handler):
        """Пропускает сообщения без пользователя."""
        from aiogram.types import Message

        message = MagicMock(spec=Message)
        message.from_user = None

        result = await middleware(handler, message, {})

        handler.assert_called_once_with(message, {})
        assert result == "handler_result"

    @pytest.mark.asyncio
    async def test_allows_all_when_db_unreachable(self, middleware, handler, message_event):
        """Пропускает всех при ошибке БД (graceful fallback)."""
        with patch("bot.middleware.get_db_session") as mock_session_ctx:
            mock_session_ctx.side_effect = Exception("DB connection failed")

            result = await middleware(handler, message_event, {})

            handler.assert_called_once_with(message_event, {})
            assert result == "handler_result"
            message_event.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_denied_access(self, middleware, handler, message_event, caplog):
        """Логирует отказ в доступе."""
        import logging

        with patch("bot.middleware.get_db_session") as mock_session_ctx, patch(
            "bot.middleware.get_all_telegram_ids", new=AsyncMock(return_value=[999])
        ):
            mock_session_ctx.return_value = self._mock_get_session([999])()

            with caplog.at_level(logging.WARNING):
                await middleware(handler, message_event, {})

            assert "Access denied" in caplog.text
            assert "123456" in caplog.text
