from pip._internal import commands

from bot.config import settings
from bot.handlers import messages, common
from aiogram import Bot, Dispatcher
import asyncio
from bot.logging_config import setup_logging

setup_logging()

async def main() -> None:
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(messages.router)
    dp.include_router(common.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

