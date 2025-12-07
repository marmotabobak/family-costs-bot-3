from bot.config import settings
from bot.handlers import start, messages
from aiogram import Bot, Dispatcher
import asyncio
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def main() -> None:
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(messages.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

