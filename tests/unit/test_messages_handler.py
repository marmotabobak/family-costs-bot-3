from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.constants import MSG_DB_ERROR, MSG_PARSE_ERROR
from bot.routers.messages import (
    CALLBACK_CANCEL,
    CALLBACK_CONFIRM,
    SaveCostsStates,
    build_confirmation_keyboard,
    format_confirmation_message,
    format_success_message,
    handle_cancel,
    handle_confirm,
    handle_message,
)
from bot.services.message_parser import Cost
from aiogram.types import Message

# ======================================================
# handle_message
# ======================================================

class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_no_text_returns_early(self, mock_message, mock_state):
        mock_message.text = None
        await handle_message(mock_message, mock_state)
        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_from_user_returns_early(self, mock_message, mock_state):
        mock_message.from_user = None
        await handle_message(mock_message, mock_state)
        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_sends_error_and_help(self, mock_message, mock_state):
        mock_message.text = "invalid message"
        await handle_message(mock_message, mock_state)

        assert mock_message.answer.call_count == 2
        assert mock_message.answer.call_args_list[0][0][0] == MSG_PARSE_ERROR

    @pytest.mark.asyncio
    async def test_db_error_sends_error_message(self, mock_message, mock_state, mock_session):
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
    async def test_success_sends_success_message(self, mock_message, mock_state, mock_session):
        saved = MagicMock()
        saved.id = 1

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_save.return_value = saved

            await handle_message(mock_message, mock_state)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]

        assert "Записано 1 расход" in text
        assert "Продукты: 100" in text

    @pytest.mark.asyncio
    async def test_mixed_lines_asks_confirmation(self, mock_message, mock_state):
        mock_message.text = "Продукты 100\nbad\nВода 50"

        await handle_message(mock_message, mock_state)

        mock_state.set_state.assert_called_once_with(SaveCostsStates.waiting_confirmation)
        mock_message.answer.assert_called_once()

        text = mock_message.answer.call_args[0][0]
        assert "bad" in text
        assert "Продукты" in text


# ======================================================
# keyboards
# ======================================================

class TestBuildConfirmationKeyboard:
    def test_has_two_buttons(self):
        keyboard = build_confirmation_keyboard()
        assert len(keyboard.inline_keyboard[0]) == 2

    def test_callback_data_correct(self):
        buttons = build_confirmation_keyboard().inline_keyboard[0]
        assert buttons[0].callback_data == CALLBACK_CONFIRM
        assert buttons[1].callback_data == CALLBACK_CANCEL


# ======================================================
# formatters
# ======================================================

class TestFormatConfirmationMessage:
    def test_contains_invalid_lines(self):
        msg = format_confirmation_message(
            [Cost("A", Decimal("1"))],
            ["bad 1", "bad 2"],
        )
        assert "bad 1" in msg
        assert "bad 2" in msg

    def test_contains_valid_costs(self):
        msg = format_confirmation_message(
            [
                Cost("Продукты", Decimal("100")),
                Cost("Вода", Decimal("50")),
            ],
            ["bad"],
        )
        assert "Продукты" in msg
        assert "100" in msg
        assert "Вода" in msg
        assert "50" in msg

    def test_contains_question(self):
        msg = format_confirmation_message(
            [Cost("A", Decimal("1"))],
            ["bad"],
        )
        assert "Записать распарсенные строки?" in msg


class TestFormatSuccessMessage:
    def test_pluralization(self):
        assert "1 расход" in format_success_message([Cost("A", Decimal("1"))])
        assert "2 расхода" in format_success_message(
            [Cost("A", Decimal("1")), Cost("A", Decimal("1"))]
        )
        assert "5 расходов" in format_success_message(
            [Cost("A", Decimal("1"))] * 5
        )


# ======================================================
# confirm / cancel
# ======================================================

class TestHandleConfirm:
    @pytest.mark.asyncio
    async def test_saves_on_confirm(self, mock_state, mock_session):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.answer = AsyncMock()
        cb.message = MagicMock(spec=Message)
        cb.message.edit_text = AsyncMock()


        mock_state.get_data.return_value = {
            "valid_costs": [Cost("Продукты", Decimal("100"))],
        }

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_confirm(cb, mock_state)

        mock_save.assert_called_once()
        cb.message.edit_text.assert_called_once()


class TestHandleCancel:
    @pytest.mark.asyncio
    async def test_cancel_clears_state(self, mock_state):
        cb = MagicMock()
        cb.answer = AsyncMock()
        cb.message = MagicMock(spec=Message)
        cb.message.edit_text = AsyncMock()

        await handle_cancel(cb, mock_state)

        mock_state.clear.assert_called_once()
        cb.message.edit_text.assert_called_once()
