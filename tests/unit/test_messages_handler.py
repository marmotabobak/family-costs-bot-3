from datetime import timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.constants import MSG_DB_ERROR, MSG_PARSE_ERROR
from bot.routers.messages import (
    CALLBACK_CANCEL_SAVE,
    CALLBACK_CONFIRM_SAVE,
    CALLBACK_UNDO_PREFIX,
    SaveCostsStates,
    build_confirmation_keyboard,
    build_success_keyboard,
    format_confirmation_message,
    format_past_mode_info,
    format_success_message,
    get_past_mode_date,
    handle_cancel_save,
    handle_confirm_save,
    handle_message,
    handle_undo,
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
        """Успешное сохранение — отправляется подтверждение со списком и кнопкой отмены."""
        mock_saved_message = MagicMock()
        mock_saved_message.id = 1

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_save.return_value = mock_saved_message

            await handle_message(mock_message, mock_state)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        # Проверяем формат: "✅ Записано 1 расход:\n\n  • Продукты: 100"
        assert "Записано 1 расход" in response
        assert "Продукты: 100" in response
        # Проверяем что есть кнопка отмены
        call_kwargs = mock_message.answer.call_args.kwargs
        assert "reply_markup" in call_kwargs

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
                created_at=None,  # По умолчанию - текущая дата
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
            # Теперь вместо clear() используется set_state(None) + update_data()
            mock_state.set_state.assert_called_with(None)
            mock_state.update_data.assert_called()
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


# ========== Тесты для режима ввода расходов в прошлое ==========


class TestGetPastModeDate:
    """Тесты функции получения даты режима ввода в прошлое."""

    def test_returns_none_when_no_data(self):
        """Возвращает None если данных нет."""
        result = get_past_mode_date({})
        assert result is None

    def test_returns_none_when_partial_data(self):
        """Возвращает None если данные неполные."""
        assert get_past_mode_date({"past_mode_year": 2024}) is None
        assert get_past_mode_date({"past_mode_month": 6}) is None

    def test_returns_first_day_of_month(self):
        """Возвращает 1-е число указанного месяца."""
        result = get_past_mode_date({"past_mode_year": 2024, "past_mode_month": 6})

        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 1
        assert result.tzinfo == timezone.utc


class TestFormatPastModeInfo:
    """Тесты форматирования информации о режиме."""

    def test_contains_month_and_year(self):
        """Содержит месяц и год."""
        result = format_past_mode_info(2024, 6)

        assert "Июнь" in result
        assert "2024" in result

    def test_contains_recorded_prefix(self):
        """Содержит информацию о записи."""
        result = format_past_mode_info(2024, 1)

        assert "Записано" in result


class TestHandleMessageWithPastMode:
    """Тесты обработчика сообщений в режиме ввода в прошлое."""

    @pytest.fixture
    def mock_message(self):
        """Мок сообщения."""
        from aiogram.types import Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.text = "Продукты 100"
        msg.from_user = user
        msg.answer = AsyncMock()

        return msg

    @pytest.fixture
    def mock_state_with_past_mode(self):
        """Мок FSMContext с активным режимом ввода в прошлое."""
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "past_mode_year": 2024,
            "past_mode_month": 6,
        })
        state.set_state = AsyncMock()
        state.update_data = AsyncMock()
        return state

    @pytest.fixture
    def mock_session(self):
        """Мок сессии БД."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_saves_with_past_date(self, mock_message, mock_state_with_past_mode, mock_session):
        """Сохраняет расходы с датой из режима."""
        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state_with_past_mode)

            # Проверяем что save_message вызван с кастомной датой
            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args.kwargs
            assert call_kwargs["created_at"] is not None
            assert call_kwargs["created_at"].year == 2024
            assert call_kwargs["created_at"].month == 6
            assert call_kwargs["created_at"].day == 1

    @pytest.mark.asyncio
    async def test_response_includes_past_mode_info(self, mock_message, mock_state_with_past_mode, mock_session):
        """Ответ содержит информацию о записи в прошлое."""
        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message"),
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state_with_past_mode)

            mock_message.answer.assert_called_once()
            call_args = mock_message.answer.call_args

            response = call_args[0][0]
            assert "Июнь 2024" in response

            # Проверяем что есть кнопка "Отключить прошлое"
            assert "reply_markup" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_normal_mode_saves_without_date(self, mock_message, mock_state, mock_session):
        """В обычном режиме сохраняет без кастомной даты."""
        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message, mock_state)

            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args.kwargs
            assert call_kwargs["created_at"] is None


# ========== Тесты для отмены действия ==========


class TestBuildSuccessKeyboard:
    """Тесты построения клавиатуры успешного сообщения."""

    def test_has_undo_button(self):
        """Клавиатура содержит кнопку отмены."""
        keyboard = build_success_keyboard([1, 2, 3])

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1
        assert "Отменить" in keyboard.inline_keyboard[0][0].text

    def test_callback_data_contains_ids(self):
        """Callback data содержит ID записей."""
        keyboard = build_success_keyboard([1, 2, 3])

        callback_data = keyboard.inline_keyboard[0][0].callback_data
        assert callback_data == f"{CALLBACK_UNDO_PREFIX}1,2,3"

    def test_with_disable_past_button(self):
        """С флагом include_disable_past добавляется вторая кнопка."""
        keyboard = build_success_keyboard([1], include_disable_past=True)

        assert len(keyboard.inline_keyboard) == 2
        assert "Отменить" in keyboard.inline_keyboard[0][0].text
        assert "Отключить прошлое" in keyboard.inline_keyboard[1][0].text


class TestFormatSuccessMessage:
    """Тесты форматирования сообщения об успехе."""

    def test_contains_count(self):
        """Сообщение содержит количество."""
        costs = [Cost(name="Продукты", amount=Decimal("100"))]
        message = format_success_message(costs, 1)

        assert "Записано 1 расход" in message

    def test_contains_costs_list(self):
        """Сообщение содержит список расходов."""
        costs = [
            Cost(name="Продукты", amount=Decimal("100")),
            Cost(name="Вода", amount=Decimal("50")),
        ]
        message = format_success_message(costs, 2)

        assert "Продукты: 100" in message
        assert "Вода: 50" in message

    def test_pluralizes_correctly(self):
        """Правильное склонение."""
        costs_2 = [Cost(name="A", amount=Decimal("1"))] * 2
        costs_5 = [Cost(name="A", amount=Decimal("1"))] * 5

        assert "2 расхода" in format_success_message(costs_2, 2)
        assert "5 расходов" in format_success_message(costs_5, 5)


class TestHandleUndo:
    """Тесты обработчика отмены записей."""

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
        cb.data = f"{CALLBACK_UNDO_PREFIX}1,2,3"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_deletes_messages(self, callback):
        """Удаляет записи из БД."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.delete_messages_by_ids") as mock_delete,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_delete.return_value = 3

            await handle_undo(callback)

            mock_delete.assert_called_once_with(mock_session, [1, 2, 3], 123)
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_success_message(self, callback):
        """Показывает сообщение об успешной отмене."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.delete_messages_by_ids") as mock_delete,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_delete.return_value = 3

            await handle_undo(callback)

            callback.message.edit_text.assert_called_once()
            message = callback.message.edit_text.call_args[0][0]
            assert "Отменено" in message
            assert "3" in message

    @pytest.mark.asyncio
    async def test_handles_invalid_callback_data(self, callback):
        """Обрабатывает некорректные данные."""
        callback.data = f"{CALLBACK_UNDO_PREFIX}invalid"

        await handle_undo(callback)

        callback.answer.assert_called_once()
        assert "Ошибка" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handles_empty_ids(self, callback):
        """Обрабатывает пустой список ID."""
        callback.data = f"{CALLBACK_UNDO_PREFIX}"

        await handle_undo(callback)

        callback.answer.assert_called_once()
        assert "Нет записей" in callback.answer.call_args[0][0]
