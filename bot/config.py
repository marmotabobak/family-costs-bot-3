from pydantic_settings import BaseSettings
from enum import Enum

class Environment(str, Enum):
    dev = "dev"
    prod = "prod"

class Settings(BaseSettings):
    bot_token: str
    database_url: str
    env: Environment = Environment.prod

    @property
    def debug(self) -> bool:
        return self.env == Environment.dev

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

settings = Settings()

