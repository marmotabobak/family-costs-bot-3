import logging
from unittest.mock import patch

from bot.logging_config import setup_logging


class TestSetupLogging:
    """Тесты настройки логирования."""

    def test_prod_level_is_info(self):
        """В prod уровень логирования INFO."""
        with patch("bot.logging_config.settings") as mock_settings:
            mock_settings.debug = False
            with patch("logging.basicConfig") as mock_config:
                setup_logging()

                mock_config.assert_called_once()
                call_kwargs = mock_config.call_args[1]
                assert call_kwargs["level"] == logging.INFO

    def test_dev_level_is_debug(self):
        """В dev/test уровень логирования DEBUG."""
        with patch("bot.logging_config.settings") as mock_settings:
            mock_settings.debug = True
            with patch("logging.basicConfig") as mock_config:
                with patch("logging.getLogger"):
                    setup_logging()

                call_kwargs = mock_config.call_args[1]
                assert call_kwargs["level"] == logging.DEBUG

    def test_format_contains_required_fields(self):
        """Формат содержит время, уровень, имя и сообщение."""
        with patch("bot.logging_config.settings") as mock_settings:
            mock_settings.debug = False
            with patch("logging.basicConfig") as mock_config:
                setup_logging()

                call_kwargs = mock_config.call_args[1]
                fmt = call_kwargs["format"]
                assert "asctime" in fmt
                assert "levelname" in fmt
                assert "name" in fmt
                assert "message" in fmt

    def test_debug_format_includes_file_info(self):
        """В debug формате есть информация о файле и строке."""
        with patch("bot.logging_config.settings") as mock_settings:
            mock_settings.debug = True
            with patch("logging.basicConfig") as mock_config:
                with patch("logging.getLogger"):
                    setup_logging()

                call_kwargs = mock_config.call_args[1]
                fmt = call_kwargs["format"]
                assert "filename" in fmt
                assert "lineno" in fmt
