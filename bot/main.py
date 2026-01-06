import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.session import engine
from bot.logging_config import setup_logging
from bot.middleware import AllowedUsersMiddleware
from bot.routers import common, menu, messages

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.MARKDOWN,
        ),
    )

    dp = Dispatcher()
    dp.message.middleware(AllowedUsersMiddleware())
    dp.include_router(messages.router)
    dp.include_router(menu.router)
    dp.include_router(common.router)

    # Graceful shutdown на SIGTERM и SIGINT
    loop = asyncio.get_event_loop()

    def signal_handler(sig: signal.Signals) -> None:
        logger.info("Received signal %s, initiating graceful shutdown...", sig.name)
        loop.create_task(shutdown(bot, dp))

    # Регистрируем обработчики сигналов
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: signal_handler(s),  # type: ignore[misc]
        )

    logger.info("Bot started. Press Ctrl+C to stop.")

    try:
        await dp.start_polling(bot)
    finally:
        await cleanup(bot)


async def shutdown(bot: Bot, dp: Dispatcher) -> None:
    """Останавливает polling."""
    logger.info("Stopping polling...")
    await dp.stop_polling()


async def cleanup(bot: Bot) -> None:
    """Освобождает ресурсы."""
    logger.info("Cleaning up resources...")

    try:
        await bot.session.close()
    except Exception as e:
        logger.warning("Error closing bot session: %s", e)

    # Закрываем connection pool БД
    await engine.dispose()

    logger.info("Bot stopped successfully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
