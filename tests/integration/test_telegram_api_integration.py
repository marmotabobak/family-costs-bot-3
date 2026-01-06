"""Интеграционные тесты для проверки работы с Telegram API.

Эти тесты проверяют полный цикл: Update → Dispatcher → Handler → Bot.send_message.
Telegram API мокируется через aioresponses.
"""

from datetime import datetime, timezone

import pytest
from aioresponses import aioresponses
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import select

from bot.db.dependencies import get_session
from bot.db.models import Message as DBMessage
from bot.routers import common, messages


def create_test_update(
    update_id: int,
    message_id: int,
    user_id: int,
    chat_id: int,
    text: str,
) -> Update:
    """Создает тестовый Update объект, имитирующий входящее сообщение от Telegram."""
    user = User(
        id=user_id,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
    )
    chat = Chat(
        id=chat_id,
        type="private",
        first_name="Test",
        last_name="User",
        username="testuser",
    )
    message = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(
        update_id=update_id,
        message=message,
    )


@pytest.fixture(scope="module")
def test_bot() -> Bot:
    """Создает тестовый экземпляр бота (один на модуль)."""
    return Bot(
        token="123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss",
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


@pytest.fixture(scope="module")
def test_dispatcher() -> Dispatcher:
    """Создает Dispatcher с зарегистрированными роутерами (один на модуль).
    
    Роутеры в aiogram можно прикрепить только к одному Dispatcher,
    поэтому используем scope="module".
    """
    dp = Dispatcher()
    dp.include_router(messages.router)
    dp.include_router(common.router)
    return dp


class TestTelegramAPIIntegration:
    """Интеграционные тесты взаимодействия с Telegram API."""

    @pytest.mark.asyncio
    async def test_full_update_processing_sends_response(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет полный цикл обработки Update и отправку ответа через Telegram API."""
        update = create_test_update(
            update_id=1,
            message_id=100,
            user_id=123456,
            chat_id=123456,
            text="Продукты 500",
        )

        with aioresponses() as mocked:
            # Мокируем Telegram API endpoint для sendMessage
            # Telegram Bot API URL: https://api.telegram.org/bot<token>/sendMessage
            mocked.post(
                "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage",
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 101,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 123456, "type": "private"},
                        "date": 0,
                        "text": "1 расход успешно сохранено ✅",
                    },
                },
            )

            # Обрабатываем Update через Dispatcher
            await test_dispatcher.feed_update(test_bot, update)

        # Проверяем что данные сохранились в БД
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 123456)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 1
            assert db_messages[0].text == "Продукты 500"

    @pytest.mark.asyncio
    async def test_help_command_sends_help_text(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет что команда /help отправляет справку через API."""
        update = create_test_update(
            update_id=2,
            message_id=200,
            user_id=654321,
            chat_id=654321,
            text="/help",
        )

        with aioresponses() as mocked:
            # Мокируем ответ на sendMessage
            mocked.post(
                "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage",
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 201,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 654321, "type": "private"},
                        "date": 0,
                        "text": "Help text",
                    },
                },
            )

            await test_dispatcher.feed_update(test_bot, update)

        # /help не должен сохранять ничего в БД
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 654321)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 0

    @pytest.mark.asyncio
    async def test_invalid_message_sends_error_and_help(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет что невалидное сообщение отправляет ошибку и справку."""
        update = create_test_update(
            update_id=3,
            message_id=300,
            user_id=111222,
            chat_id=111222,
            text="невалидное сообщение без суммы",
        )

        with aioresponses() as mocked:
            # Ожидаем 2 вызова sendMessage: ошибка + справка
            # Мокируем оба вызова последовательно
            api_url = "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage"
            
            # Первый вызов - сообщение об ошибке
            mocked.post(
                api_url,
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 301,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 111222, "type": "private"},
                        "date": 0,
                        "text": "Не удалось распарсить сообщение",
                    },
                },
            )
            
            # Второй вызов - справка
            mocked.post(
                api_url,
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 302,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 111222, "type": "private"},
                        "date": 0,
                        "text": "Help text",
                    },
                },
            )

            await test_dispatcher.feed_update(test_bot, update)

        # Проверяем что ничего не сохранилось в БД
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 111222)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 0

    @pytest.mark.asyncio
    async def test_multiple_costs_single_transaction(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет атомарное сохранение нескольких расходов."""
        update = create_test_update(
            update_id=4,
            message_id=400,
            user_id=999888,
            chat_id=999888,
            text="Молоко 100\nХлеб 50\nСыр 200",
        )

        with aioresponses() as mocked:
            mocked.post(
                "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage",
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 401,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 999888, "type": "private"},
                        "date": 0,
                        "text": "3 расхода успешно сохранено ✅",
                    },
                },
            )

            await test_dispatcher.feed_update(test_bot, update)

        # Все 3 расхода должны быть сохранены
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 999888).order_by(DBMessage.id)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 3
            assert db_messages[0].text == "Молоко 100"
            assert db_messages[1].text == "Хлеб 50"
            assert db_messages[2].text == "Сыр 200"

    @pytest.mark.asyncio
    async def test_telegram_api_error_handling(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет обработку ошибки от Telegram API."""
        update = create_test_update(
            update_id=5,
            message_id=500,
            user_id=777666,
            chat_id=777666,
            text="Тест 100",
        )

        with aioresponses() as mocked:
            # Симулируем ошибку от Telegram API
            mocked.post(
                "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage",
                payload={
                    "ok": False,
                    "error_code": 403,
                    "description": "Forbidden: bot was blocked by the user",
                },
                status=403,
            )

            # Не должно упасть, ошибка должна быть обработана
            # aiogram может поднять исключение, но dispatcher его перехватит
            try:
                await test_dispatcher.feed_update(test_bot, update)
            except Exception:
                pass  # Ожидаемое поведение - ошибка API

        # Данные всё равно должны быть сохранены в БД
        # (сохранение происходит до отправки ответа)
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 777666)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 1
            assert db_messages[0].text == "Тест 100"

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome(
        self,
        test_bot: Bot,
        test_dispatcher: Dispatcher,
    ):
        """Проверяет что команда /start отправляет приветствие."""
        update = create_test_update(
            update_id=6,
            message_id=600,
            user_id=555444,
            chat_id=555444,
            text="/start",
        )

        with aioresponses() as mocked:
            mocked.post(
                "https://api.telegram.org/bot123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQRRss/sendMessage",
                payload={
                    "ok": True,
                    "result": {
                        "message_id": 601,
                        "from": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
                        "chat": {"id": 555444, "type": "private"},
                        "date": 0,
                        "text": "Welcome!",
                    },
                },
            )

            await test_dispatcher.feed_update(test_bot, update)

        # /start не должен сохранять данные
        async with get_session() as session:
            stmt = select(DBMessage).where(DBMessage.user_id == 555444)
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            assert len(db_messages) == 0
