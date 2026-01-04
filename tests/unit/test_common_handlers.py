import pytest
from aiogram.enums import ParseMode

from bot.constants import HELP_TEXT, START_GREETING
from bot.routers.common import start, help_


class TestCommonHandlers:
    """Тесты обработчиков /start и /help."""

    @pytest.mark.asyncio
    async def test_start_sends_greeting_and_help(self, mock_message):
        """Команда /start отправляет приветствие и справку."""
        await start(mock_message)

        mock_message.answer.assert_called_once_with(
            START_GREETING + HELP_TEXT,
            parse_mode=ParseMode.MARKDOWN,
        )

    @pytest.mark.asyncio
    async def test_help_sends_help_text(self, mock_message):
        """Команда /help отправляет справку."""
        await help_(mock_message)

        mock_message.answer.assert_called_once_with(
            HELP_TEXT,
            parse_mode=ParseMode.MARKDOWN,
        )
