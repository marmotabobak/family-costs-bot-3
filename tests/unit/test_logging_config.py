import logging
from unittest.mock import patch, MagicMock

from bot.logging_config import setup_logging
from bot.config import Environment


class TestSetupLogging:
    """Тесты настройки логирования."""

    def test_default_level_is_info(self):
        """По умолчанию уровень логирования INFO (prod mode)."""
        with patch("bot.logging_config.settings") as mock_settings, \
             patch("logging.basicConfig") as mock_config:
            mock_settings.env.value = "prod"
            setup_logging()

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_custom_level(self):
        """В DEV mode уровень логирования DEBUG."""
        with patch("bot.logging_config.settings") as mock_settings, \
             patch("logging.basicConfig") as mock_config:
            mock_settings.env.value = "dev"
            setup_logging()

            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_format_contains_required_fields(self):
        """Формат содержит время, уровень, имя и сообщение."""
        with patch("bot.logging_config.settings") as mock_settings, \
             patch("logging.basicConfig") as mock_config:
            mock_settings.env.value = "prod"
            setup_logging()

            call_kwargs = mock_config.call_args[1]
            fmt = call_kwargs["format"]
            assert "asctime" in fmt
            assert "levelname" in fmt
            assert "name" in fmt
            assert "message" in fmt
