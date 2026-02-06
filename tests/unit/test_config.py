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


class TestAdminTelegramId:
    """Тесты настройки admin_telegram_id."""

    def test_admin_telegram_id_default_none(self):
        """По умолчанию admin_telegram_id не задан."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.admin_telegram_id is None

    def test_admin_telegram_id_from_value(self):
        """admin_telegram_id принимается явно."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            admin_telegram_id=123456789,
        )
        assert settings.admin_telegram_id == 123456789

    def test_admin_telegram_id_from_env(self, monkeypatch):
        """admin_telegram_id читается из переменной окружения."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        monkeypatch.setenv("ADMIN_TELEGRAM_ID", "987654321")
        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.admin_telegram_id == 987654321


class TestWebSettings:
    """Тесты настроек web-сервера."""

    def test_web_password_default_empty(self):
        """По умолчанию пароль пуст."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.web_password == ""

    def test_web_password_from_value(self):
        """Пароль принимается явно."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            web_password="my-secret",
        )
        assert settings.web_password == "my-secret"

    def test_web_password_from_env(self, monkeypatch):
        """Пароль читается из переменной окружения WEB_PASSWORD."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        monkeypatch.setenv("WEB_PASSWORD", "from-env")
        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.web_password == "from-env"

    def test_web_base_url_default(self):
        """По умолчанию базовый URL localhost:8000."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.web_base_url == "http://localhost:8000"

    def test_web_base_url_from_value(self):
        """Базовый URL принимается явно."""
        settings = Settings(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
            web_base_url="https://example.com",
        )
        assert settings.web_base_url == "https://example.com"

    def test_web_base_url_from_env(self, monkeypatch):
        """Базовый URL читается из переменной окружения WEB_BASE_URL."""

        class SettingsWithNoEnv(Settings):
            model_config = SettingsConfigDict(env_file=None)

        monkeypatch.setenv("WEB_BASE_URL", "https://prod.example.com")
        settings = SettingsWithNoEnv(
            bot_token="123456789:ABCdefGHIjkl",
            database_url="postgresql://user:pass@localhost/db",
        )
        assert settings.web_base_url == "https://prod.example.com"
