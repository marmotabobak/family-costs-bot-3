import logging
import sys

from bot.config import settings


def setup_logging() -> None:
    """Setup logging configuration based on environment."""
    # Determine log level based on environment
    if settings.env.value == "dev":
        level = logging.DEBUG
        # Detailed format for DEV mode
        format_str = (
            "%(asctime)s | %(levelname)-8s | %(name)-30s | "
            "%(filename)s:%(lineno)d | %(funcName)s() | %(message)s"
        )
    elif settings.env.value == "test":
        level = logging.INFO
        format_str = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    else:  # prod
        level = logging.INFO
        format_str = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"

    # Configure root logger
    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,  # Override any existing configuration
    )

    # Set specific loggers to appropriate levels
    if settings.env.value == "dev":
        # Enable DEBUG for our modules
        logging.getLogger("bot").setLevel(logging.DEBUG)
        # Enable SQLAlchemy query logging
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.dialects").setLevel(logging.INFO)
        # Reduce noise from third-party libraries
        logging.getLogger("aiogram").setLevel(logging.INFO)
        logging.getLogger("aiogram.event").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
    else:
        # Production: only INFO and above
        logging.getLogger("bot").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
        logging.getLogger("aiogram").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured: level=%s, env=%s",
        logging.getLevelName(level),
        settings.env.value,
    )
