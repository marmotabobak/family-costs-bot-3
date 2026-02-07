from enum import Enum

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    dev = "dev"
    test = "test"
    prod = "prod"


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    env: Environment = Environment.prod
    admin_telegram_id: int | None = None
    web_base_url: str = "http://localhost:8000"
    admin_default_password: str = ""
    web_root_path: str = ""

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Валидация токена Telegram бота."""
        if not v:
            raise ValueError("BOT_TOKEN не может быть пустым")

        # Telegram токены имеют формат: 123456:ABC-DEF...
        # Минимальная длина ~45 символов
        if len(v) < 20:
            raise ValueError("BOT_TOKEN слишком короткий (минимум 20 символов)")

        if ":" not in v:
            raise ValueError("BOT_TOKEN должен содержать ':' (формат: bot_id:token)")

        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Валидация URL подключения к БД."""
        if not v:
            raise ValueError("DATABASE_URL не может быть пустым")

        # Проверяем что это PostgreSQL
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL должен начинаться с 'postgresql://' или 'postgresql+asyncpg://'")

        return v

    @property
    def debug(self) -> bool:
        return self.env in (Environment.dev, Environment.test)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
