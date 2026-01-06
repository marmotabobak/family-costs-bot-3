from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.constants import MSG_DB_ERROR, MSG_PARSE_ERROR, MSG_SUCCESS
from bot.routers.messages import (
    CALLBACK_CANCEL_SAVE,
    CALLBACK_CONFIRM_SAVE,
    SaveCostsStates,
    build_confirmation_keyboard,
    format_confirmation_message,
    handle_cancel_save,
    handle_confirm_save,
    handle_message,
)
from bot.services.message_parser import Cost


class TestHandleMessage:
    """Тесты обработчика сообщений."""

    @pytest.mark.asyncio
    async def test_no_text_returns_early(self, mock_message, mock_state):
        """Если нет текста, хэндлер завершается без ответа."""
        mock_message.text = None

        await handle_message(mock_message, mock_state)

        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_from_user_returns_early(self, mock_message, mock_state):
        """Если нет from_user, хэндлер завершается без ответа."""
        mock_message.from_user = None

        await handle_message(mock_message, mock_state)

        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_sends_error_and_help(self, mock_message, mock_state):
        """Если формат невалидный, отправляется ошибка и справка."""
        mock_message.text = "invalid message without amount"

        await handle_message(mock_message, mock_state)

        assert mock_message.answer.call_count == 2
        first_call = mock_message.answer.call_args_list[0]
        assert first_call[0][0] == MSG_PARSE_ERROR

    @pytest.mark.asyncio
    async def test_db_error_sends_error_message(self, mock_message, mock_state, mock_session):
        """Если БД недоступна, отправляется сообщение об ошибке."""
        from sqlalchemy.exc import SQLAlchemyError

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_save.side_effect = SQLAlchemyError("DB error")

            await handle_message(mock_message, mock_state)

        mock_message.answer.assert_called_once_with(MSG_DB_ERROR)

    @pytest.mark.asyncio
    async def test_success_sends_confirmation(self, mock_message, mock_state, mock_session):
        """Успешное сохранение — отправляется подтверждение."""
        with patch("bot.routers.messages.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert response == MSG_SUCCESS.format(count=1, word="расход")

    @pytest.mark.asyncio
    async def test_mixed_lines_asks_confirmation(self, mock_message, mock_state, mock_session):
        """Частично валидное сообщение — запрашивается подтверждение."""
        mock_message.text = "Продукты 100\ninvalid line\nВода 50"

        await handle_message(mock_message, mock_state)

        # Проверяем что установлено состояние FSM
        mock_state.set_state.assert_called_once_with(SaveCostsStates.waiting_confirmation)

        # Проверяем что данные сохранены в FSM
        mock_state.update_data.assert_called_once()

        # Проверяем что отправлен запрос подтверждения с клавиатурой
        mock_message.answer.assert_called_once()
        call_kwargs = mock_message.answer.call_args.kwargs
        assert "reply_markup" in call_kwargs

        response = mock_message.answer.call_args[0][0]
        assert "invalid line" in response
        assert "Продукты" in response

    @pytest.mark.asyncio
    async def test_save_message_called_with_correct_args(self, mock_message, mock_state, mock_session):
        """save_message вызывается с правильными аргументами."""
        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state)

            mock_save.assert_called_once_with(
                session=mock_session,
                user_id=123,
                text="Продукты 100",
            )

    @pytest.mark.asyncio
    async def test_multiple_costs_calls_save_for_each(self, mock_message, mock_state, mock_session):
        """Несколько расходов — save_message вызывается для каждого."""
        mock_message.text = "Продукты 100\nВода 50\nХлеб 30"

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state)

            assert mock_save.call_count == 3
            mock_session.commit.assert_called_once()


class TestBuildConfirmationKeyboard:
    """Тесты построения клавиатуры подтверждения."""

    def test_has_two_buttons(self):
        """Клавиатура содержит две кнопки."""
        keyboard = build_confirmation_keyboard()

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

    def test_callback_data(self):
        """Проверка callback_data кнопок."""
        keyboard = build_confirmation_keyboard()

        buttons = keyboard.inline_keyboard[0]
        callback_datas = [b.callback_data for b in buttons]

        assert CALLBACK_CONFIRM_SAVE in callback_datas
        assert CALLBACK_CANCEL_SAVE in callback_datas


class TestFormatConfirmationMessage:
    """Тесты форматирования сообщения подтверждения."""

    def test_contains_invalid_lines(self):
        """Сообщение содержит невалидные строки."""
        valid = [Cost(name="Продукты", amount=Decimal("100"))]
        invalid = ["bad line 1", "bad line 2"]

        message = format_confirmation_message(valid, invalid)

        assert "bad line 1" in message
        assert "bad line 2" in message

    def test_contains_valid_costs(self):
        """Сообщение содержит валидные расходы."""
        valid = [
            Cost(name="Продукты", amount=Decimal("100")),
            Cost(name="Вода", amount=Decimal("50")),
        ]
        invalid = ["bad"]

        message = format_confirmation_message(valid, invalid)

        assert "Продукты" in message
        assert "100" in message
        assert "Вода" in message
        assert "50" in message

    def test_contains_count_question(self):
        """Сообщение содержит вопрос с количеством."""
        valid = [Cost(name="Продукты", amount=Decimal("100"))]
        invalid = ["bad"]

        message = format_confirmation_message(valid, invalid)

        assert "Записать 1 расход?" in message


class TestHandleConfirmSave:
    """Тесты обработчика подтверждения сохранения."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.edit_text = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_CONFIRM_SAVE
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_saves_costs_on_confirm(self, callback, mock_state, mock_session):
        """При подтверждении сохраняет расходы."""
        mock_state.get_data.return_value = {
            "valid_costs": [{"name": "Продукты", "amount": "100"}],
            "invalid_lines": ["bad"],
        }

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_confirm_save(callback, mock_state)

            mock_save.assert_called_once()
            mock_state.clear.assert_called_once()
            callback.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_clears_state_on_no_data(self, callback, mock_state):
        """Очищает состояние если нет данных."""
        mock_state.get_data.return_value = {}

        await handle_confirm_save(callback, mock_state)

        mock_state.clear.assert_called_once()
        callback.answer.assert_called_once_with("Нет данных для сохранения")


class TestHandleCancelSave:
    """Тесты обработчика отмены сохранения."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.edit_text = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_CANCEL_SAVE
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_clears_state_on_cancel(self, callback, mock_state):
        """При отмене очищает состояние."""
        await handle_cancel_save(callback, mock_state)

        mock_state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_cancel_message(self, callback, mock_state):
        """При отмене показывает сообщение об отмене."""
        await handle_cancel_save(callback, mock_state)

        callback.message.edit_text.assert_called_once()
        message = callback.message.edit_text.call_args[0][0]
        assert "отменено" in message.lower()
