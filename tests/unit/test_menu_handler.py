"""Тесты для роутера меню."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.routers.menu import (
    CALLBACK_MY_COSTS,
    CALLBACK_USER_COSTS_PREFIX,
    build_menu_keyboard,
    handle_my_costs,
    handle_user_costs,
    menu_command,
)


class TestBuildMenuKeyboard:
    """Тесты построения клавиатуры меню."""

    def test_empty_user_list(self):
        """Пустой список пользователей - только кнопка 'Мои расходы'."""
        keyboard = build_menu_keyboard(current_user_id=123, all_user_ids=[])

        assert len(keyboard.inline_keyboard) == 1
        assert keyboard.inline_keyboard[0][0].text == "📊 Мои расходы"
        assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_MY_COSTS

    def test_current_user_excluded(self):
        """Текущий пользователь не показывается в списке."""
        keyboard = build_menu_keyboard(current_user_id=123, all_user_ids=[123, 456, 789])

        # Должна быть кнопка "Мои расходы" + 2 кнопки для других пользователей
        assert len(keyboard.inline_keyboard) == 3

        # Проверяем что нет кнопки для user_id=123
        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" not in callback_datas

    def test_all_users_shown(self):
        """Все пользователи кроме текущего показаны."""
        keyboard = build_menu_keyboard(current_user_id=100, all_user_ids=[123, 456, 789])

        assert len(keyboard.inline_keyboard) == 4  # Мои расходы + 3 пользователя

        # Проверяем callback_data для каждого пользователя
        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard[1:]]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}456" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}789" in callback_datas

    def test_button_text_contains_user_id(self):
        """Текст кнопки содержит user_id."""
        keyboard = build_menu_keyboard(current_user_id=100, all_user_ids=[123])

        user_button = keyboard.inline_keyboard[1][0]
        assert "123" in user_button.text


class TestMenuCommand:
    """Тесты команды /menu."""

    @pytest.fixture
    def message(self):
        """Фикстура сообщения."""
        from aiogram.types import Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.answer = AsyncMock()

        return msg

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.from_user = None
        msg.answer = AsyncMock()

        await menu_command(msg)

        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_menu_with_keyboard(self, message):
        """Отправляет меню с клавиатурой."""
        mock_session = AsyncMock()

        with patch("bot.routers.menu.get_session") as mock_get_session, \
             patch("bot.routers.menu.get_unique_user_ids") as mock_get_users:

            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_users.return_value = [123, 456]

            await menu_command(message)

            message.answer.assert_called_once()
            call_kwargs = message.answer.call_args.kwargs
            assert "reply_markup" in call_kwargs
            assert call_kwargs["reply_markup"] is not None


class TestHandleMyCosts:
    """Тесты обработчика 'Мои расходы'."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_MY_COSTS
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.answer = AsyncMock()

        await handle_my_costs(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_stub_message(self, callback):
        """Отправляет заглушку."""
        await handle_my_costs(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        response = callback.message.answer.call_args[0][0]
        assert "разработке" in response
        assert "123" in response


class TestHandleUserCosts:
    """Тесты обработчика 'Расходы <user_id>'."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = f"{CALLBACK_USER_COSTS_PREFIX}456"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.data = None
        cb.answer = AsyncMock()

        await handle_user_costs(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_stub_message_with_target_user(self, callback):
        """Отправляет заглушку с user_id целевого пользователя."""
        await handle_user_costs(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        response = callback.message.answer.call_args[0][0]
        assert "разработке" in response
        assert "456" in response  # target user_id
