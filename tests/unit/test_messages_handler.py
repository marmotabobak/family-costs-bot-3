from unittest.mock import patch
import pytest

from bot.constants import MSG_DB_ERROR, MSG_DB_PARTIAL_ERROR, MSG_INVALID_LINES, MSG_PARSE_ERROR, MSG_SUCCESS
from bot.routers.messages import handle_message


class TestHandleMessage:
    """Тесты обработчика сообщений."""

    @pytest.mark.asyncio
    async def test_no_text_returns_early(self, mock_message):
        """Если нет текста, хэндлер завершается без ответа."""
        mock_message.text = None

        await handle_message(mock_message)

        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_from_user_returns_early(self, mock_message):
        """Если нет from_user, хэндлер завершается без ответа."""
        mock_message.from_user = None

        await handle_message(mock_message)

        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_sends_error_and_help(self, mock_message):
        """Если формат невалидный, отправляется ошибка и справка."""
        mock_message.text = "invalid message without amount"

        await handle_message(mock_message)

        assert mock_message.answer.call_count == 2
        first_call = mock_message.answer.call_args_list[0]
        assert first_call[0][0] == MSG_PARSE_ERROR

    @pytest.mark.asyncio
    async def test_db_error_sends_error_message(self, mock_message, mock_session):
        """Если БД полностью недоступна, отправляется сообщение об ошибке."""
        from sqlalchemy.exc import SQLAlchemyError

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_save.side_effect = SQLAlchemyError("DB error")

            await handle_message(mock_message)

        mock_message.answer.assert_called_once_with(MSG_DB_ERROR)

    @pytest.mark.asyncio
    async def test_success_sends_confirmation(self, mock_message, mock_session):
        """Успешное сохранение — отправляется подтверждение."""
        with patch("bot.routers.messages.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert response == MSG_SUCCESS.format(count=1, word="расход")

    @pytest.mark.asyncio
    async def test_mixed_lines_shows_invalid_and_success(self, mock_message, mock_session):
        """Частично валидное сообщение — выводятся ошибки и успех."""
        mock_message.text = "Продукты 100\ninvalid line\nВода 50"

        with patch("bot.routers.messages.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message)

        response = mock_message.answer.call_args[0][0]
        assert MSG_INVALID_LINES.format(lines="invalid line") in response
        assert MSG_SUCCESS.format(count=2, word="расхода") in response

    @pytest.mark.asyncio
    async def test_save_message_called_with_correct_args(self, mock_message, mock_session):
        """save_message вызывается с правильными аргументами."""
        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message)

            mock_save.assert_called_once_with(
                session=mock_session,
                user_id=123,
                text="Продукты 100",
            )

    @pytest.mark.asyncio
    async def test_multiple_costs_calls_save_for_each(self, mock_message, mock_session):
        """Несколько расходов — save_message вызывается для каждого."""
        mock_message.text = "Продукты 100\nВода 50\nХлеб 30"

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            await handle_message(mock_message)

            assert mock_save.call_count == 3

    @pytest.mark.asyncio
    async def test_partial_save_shows_failed_costs(self, mock_message, mock_session):
        """Частичное сохранение — показывает какие расходы не сохранились."""
        from sqlalchemy.exc import SQLAlchemyError

        mock_message.text = "Продукты 100\nВода 50\nХлеб 30"

        with (
            patch("bot.routers.messages.get_session") as mock_get_session,
            patch("bot.routers.messages.save_message") as mock_save,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            # Второй вызов падает с ошибкой БД
            mock_save.side_effect = [None, SQLAlchemyError("DB error"), None]

            await handle_message(mock_message)

            # Проверяем что было 3 попытки сохранения (по одной на каждый расход)
            assert mock_save.call_count == 3

        response = mock_message.answer.call_args[0][0]
        # Проверяем что показаны неудачные расходы
        assert MSG_DB_PARTIAL_ERROR.format(lines="- Вода 50") in response
        # И успешные
        assert MSG_SUCCESS.format(count=2, word="расхода") in response
