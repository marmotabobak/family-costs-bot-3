import logging
import sys

from bot.config import settings


def setup_logging() -> None:
    """Configure logging based on environment.

    - dev/test: DEBUG level, detailed format with file/line info
    - prod: INFO level, compact format
    """
    if settings.debug:
        level = logging.DEBUG
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    else:
        level = logging.INFO
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        stream=sys.stdout,
    )

    # Reduce noise from third-party libraries in debug mode
    if settings.debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("aiogram").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
