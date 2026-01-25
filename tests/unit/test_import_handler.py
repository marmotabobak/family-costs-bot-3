"""Tests for /import command handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.routers.import_cmd import import_command


class TestImportCommand:
    """Tests for /import command."""

    @pytest.fixture
    def mock_message(self):
        """Create mock message with from_user."""
        message = AsyncMock()
        message.from_user = MagicMock()
        message.from_user.id = 123456
        message.answer = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_import_sends_message_with_keyboard(self, mock_message):
        """Import command sends message with inline keyboard."""
        with patch("bot.routers.import_cmd.generate_import_token") as mock_gen_token:
            mock_gen_token.return_value = "test-token-123"

            await import_command(mock_message)

            mock_message.answer.assert_called_once()
            call_kwargs = mock_message.answer.call_args[1]
            assert "reply_markup" in call_kwargs

    @pytest.mark.asyncio
    async def test_import_generates_token_for_user(self, mock_message):
        """Import command generates token with user ID."""
        with patch("bot.routers.import_cmd.generate_import_token") as mock_gen_token:
            mock_gen_token.return_value = "test-token-123"

            await import_command(mock_message)

            mock_gen_token.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_import_url_contains_token(self, mock_message):
        """Import URL in keyboard contains generated token."""
        with patch("bot.routers.import_cmd.generate_import_token") as mock_gen_token:
            mock_gen_token.return_value = "test-token-abc"
            with patch("bot.routers.import_cmd.settings") as mock_settings:
                mock_settings.web_base_url = "http://test.com"

                await import_command(mock_message)

                # Get the keyboard from the call
                call_kwargs = mock_message.answer.call_args[1]
                keyboard = call_kwargs["reply_markup"]
                button = keyboard.inline_keyboard[0][0]

                assert "test-token-abc" in button.url
                assert button.url == "http://test.com/import/test-token-abc"

    @pytest.mark.asyncio
    async def test_import_returns_early_without_user(self):
        """Import command returns early if no from_user."""
        message = AsyncMock()
        message.from_user = None
        message.answer = AsyncMock()

        await import_command(message)

        message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_message_contains_text(self, mock_message):
        """Import message contains expected text."""
        with patch("bot.routers.import_cmd.generate_import_token") as mock_gen_token:
            mock_gen_token.return_value = "test-token-123"

            await import_command(mock_message)

            call_args = mock_message.answer.call_args[0]
            message_text = call_args[0]
            assert "Импорт" in message_text or "импорт" in message_text.lower()
