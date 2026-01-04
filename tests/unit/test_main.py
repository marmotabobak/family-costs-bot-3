from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bot.main import main


class TestMain:
    """Тесты главной функции приложения."""

    @pytest.mark.asyncio
    async def test_creates_bot_with_token(self):
        """Создаёт бота с токеном из настроек."""
        with (
            patch("bot.main.Bot") as mock_bot_class,
            patch("bot.main.Dispatcher") as mock_dp_class,
            patch("bot.main.settings") as mock_settings,
        ):
            mock_settings.bot_token = "test-token"
            mock_dp = MagicMock()
            mock_dp.start_polling = AsyncMock()
            mock_dp_class.return_value = mock_dp

            await main()

            mock_bot_class.assert_called_once()
            call_kwargs = mock_bot_class.call_args[1]
            assert call_kwargs["token"] == "test-token"

    @pytest.mark.asyncio
    async def test_includes_routers(self):
        """Подключает роутеры messages и common."""
        with (
            patch("bot.main.Bot"),
            patch("bot.main.Dispatcher") as mock_dp_class,
            patch("bot.main.messages") as mock_messages,
            patch("bot.main.common") as mock_common,
        ):
            mock_dp = MagicMock()
            mock_dp.start_polling = AsyncMock()
            mock_dp_class.return_value = mock_dp

            await main()

            mock_dp.include_router.assert_any_call(mock_messages.router)
            mock_dp.include_router.assert_any_call(mock_common.router)

    @pytest.mark.asyncio
    async def test_starts_polling(self):
        """Запускает polling."""
        with (
            patch("bot.main.Bot") as mock_bot_class,
            patch("bot.main.Dispatcher") as mock_dp_class,
        ):
            mock_bot = MagicMock()
            mock_bot_class.return_value = mock_bot
            mock_dp = MagicMock()
            mock_dp.start_polling = AsyncMock()
            mock_dp_class.return_value = mock_dp

            await main()

            mock_dp.start_polling.assert_called_once_with(mock_bot)
