import logging
from unittest.mock import patch

from bot.logging_config import setup_logging


class TestSetupLogging:
    """Тесты настройки логирования."""

    def test_default_level_is_info(self):
        """По умолчанию уровень логирования INFO."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging()

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_custom_level(self):
        """Можно задать кастомный уровень."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging(level=logging.DEBUG)

            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_format_contains_required_fields(self):
        """Формат содержит время, уровень, имя и сообщение."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging()

            call_kwargs = mock_config.call_args[1]
            fmt = call_kwargs["format"]
            assert "asctime" in fmt
            assert "levelname" in fmt
            assert "name" in fmt
            assert "message" in fmt
