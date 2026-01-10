import pytest
from pydantic import ValidationError

from bot.config import Settings
from pydantic_settings import SettingsConfigDict


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


class TestAllowedUserIdsValidation:
    """Тесты валидации allowed_user_ids."""

    def test_allowed_user_ids_default_empty(self, monkeypatch):
        """По умолчанию список разрешённых пользователей пуст."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(
                env_file=None,
            )

        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )

        assert settings.allowed_user_ids == []

    def test_allowed_user_ids_from_list(self):
        """Список пользователей из списка."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            allowed_user_ids=[123, 456, 789],
        )
        assert settings.allowed_user_ids == [123, 456, 789]

    def test_allowed_user_ids_from_comma_separated_string(self):
        """Список пользователей из строки с разделителем-запятой."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            allowed_user_ids="123,456,789",
        )
        assert settings.allowed_user_ids == [123, 456, 789]

    def test_allowed_user_ids_from_string_with_spaces(self):
        """Список пользователей из строки с пробелами."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            allowed_user_ids="123, 456,  789",
        )
        assert settings.allowed_user_ids == [123, 456, 789]

    def test_allowed_user_ids_empty_string(self):
        """Пустая строка даёт пустой список."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            allowed_user_ids="",
        )
        assert settings.allowed_user_ids == []

    def test_allowed_user_ids_single_value(self):
        """Одно значение в строке."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            allowed_user_ids="123456789",
        )
        assert settings.allowed_user_ids == [123456789]
