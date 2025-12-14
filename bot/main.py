import asyncio

from aiogram import Bot, Dispatcher

from bot.config import settings
from bot.logging_config import setup_logging
from bot.routers import messages, common

setup_logging()

async def main() -> None:
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(messages.router)
    dp.include_router(common.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

