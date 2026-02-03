from enum import Enum

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    dev = "dev"
    test = "test"
    prod = "prod"


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    env: Environment = Environment.prod
    allowed_user_ids: list[int] | str = Field(default_factory=list)
    web_base_url: str = "http://localhost:8000"
    web_password: str = ""

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v: Any) -> list[int]:
        """Парсинг списка разрешённых telegram user_id из строки или списка."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if not v or not v.strip():
            return []
        # Парсим строку вида "123,456,789" или "123, 456, 789"
        return [int(uid.strip()) for uid in v.split(",") if uid.strip()]

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
