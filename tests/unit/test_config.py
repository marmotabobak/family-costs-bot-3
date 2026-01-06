import pytest
from pydantic import ValidationError

from bot.config import Settings


class TestSettingsValidation:
    """Тесты валидации настроек."""

    def test_valid_settings(self):
        """Корректные настройки проходят валидацию."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
            database_url="postgresql+asyncpg://user:pass@localhost/db",
        )
        assert settings.bot_token
        assert settings.database_url

    def test_empty_bot_token_raises_error(self):
        """Пустой токен вызывает ошибку."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                bot_token="",
                database_url="postgresql://user:pass@localhost/db",
            )
        assert "BOT_TOKEN не может быть пустым" in str(exc_info.value)

    def test_short_bot_token_raises_error(self):
        """Короткий токен вызывает ошибку."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                bot_token="123",
                database_url="postgresql://user:pass@localhost/db",
            )
        assert "слишком короткий" in str(exc_info.value)

    def test_bot_token_without_colon_raises_error(self):
        """Токен без ':' вызывает ошибку."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                bot_token="12345678901234567890",
                database_url="postgresql://user:pass@localhost/db",
            )
        assert "должен содержать ':'" in str(exc_info.value)

    def test_empty_database_url_raises_error(self):
        """Пустой URL БД вызывает ошибку."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                bot_token="123456789:ABCdefGHIjkl",
                database_url="",
            )
        assert "DATABASE_URL не может быть пустым" in str(exc_info.value)

    def test_invalid_database_url_raises_error(self):
        """Некорректный URL БД вызывает ошибку."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                bot_token="123456789:ABCdefGHIjkl",
                database_url="mysql://user:pass@localhost/db",
            )
        assert "должен начинаться с 'postgresql://'" in str(exc_info.value)

    def test_postgresql_url_without_asyncpg_is_valid(self):
        """URL с postgresql:// (без asyncpg) также валиден."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.database_url == "postgresql://user:pass@localhost/db"
