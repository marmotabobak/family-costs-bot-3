from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

router = Router()

HELP_TEXT = """Формат сообщения:
```
расход сумма
расход сумма
...
```
Сумма: целое или вещественное (разделитель . или ,) число.
Может быть отрицательным (для корректировки).

Примеры:
- Продукты 100
- вода из Лавки 123.56
  морковь 123,00
  заказ из Озона №12345 234
  корректировка расхода -500.24
"""

@router.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет! Я бот для учёта расходов.")
    await message.answer(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("help"))
async def help_(message: Message):
    await message.answer(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)
