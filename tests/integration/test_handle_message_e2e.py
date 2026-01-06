"""E2E тесты для handle_message с реальной БД."""

import pytest
from sqlalchemy import select

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.routers.messages import handle_message


class MockUser:
    """Мок для User из aiogram."""

    def __init__(self, user_id: int):
        self.id = user_id


class MockMessage:
    """Мок для Message из aiogram с минимальным функционалом."""

    def __init__(self, text: str, user_id: int):
        self.text = text
        self.from_user = MockUser(user_id)
        self.answers: list[dict] = []  # Сохраняем все вызовы answer()

    async def answer(self, text: str, **kwargs):
        """Сохраняет ответ вместо отправки."""
        self.answers.append({"text": text, "kwargs": kwargs})


class TestHandleMessageE2E:
    """E2E тесты обработчика сообщений с реальной БД."""

    @pytest.mark.asyncio
    async def test_successful_single_cost_saves_to_db(self):
        """Успешное сохранение одного расхода в реальную БД."""
        mock_message = MockMessage("Продукты 100", user_id=12345)

        await handle_message(mock_message)

        # Проверяем что сохранилось в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 12345)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 1
            assert messages[0].text == "Продукты 100"
            assert messages[0].user_id == 12345

        # Проверяем ответ пользователю
        assert len(mock_message.answers) == 1
        assert "1 расход успешно сохранено" in mock_message.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_multiple_costs_saves_all_to_db(self):
        """Несколько расходов сохраняются в БД атомарно."""
        mock_message = MockMessage("Продукты 100\nВода 50\nХлеб 30", user_id=54321)

        await handle_message(mock_message)

        # Проверяем что все сохранились
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 54321).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 3
            assert messages[0].text == "Продукты 100"
            assert messages[1].text == "Вода 50"
            assert messages[2].text == "Хлеб 30"

        # Проверяем ответ
        assert len(mock_message.answers) == 1
        assert "3 расхода успешно сохранено" in mock_message.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_invalid_format_does_not_save_to_db(self):
        """Невалидное сообщение не сохраняется в БД."""
        mock_message = MockMessage("invalid message without amount", user_id=99999)

        await handle_message(mock_message)

        # Проверяем что ничего не сохранилось
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 99999)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 0

        # Проверяем что отправлены ошибка и справка
        assert len(mock_message.answers) == 2
        assert "Не удалось распарсить сообщение" in mock_message.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_lines(self):
        """Частично валидное сообщение сохраняет валидные строки."""
        mock_message = MockMessage(
            "Продукты 100\ninvalid line\nВода 50",
            user_id=11111,
        )

        await handle_message(mock_message)

        # Проверяем что сохранились только валидные
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 11111).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 2
            assert messages[0].text == "Продукты 100"
            assert messages[1].text == "Вода 50"

        # Проверяем ответ - должен содержать и warning, и success
        assert len(mock_message.answers) == 1
        response = mock_message.answers[0]["text"]
        assert "Не удалось распарсить строки" in response
        assert "invalid line" in response
        assert "2 расхода успешно сохранено" in response

    @pytest.mark.asyncio
    async def test_no_text_does_not_crash(self):
        """Сообщение без текста не вызывает ошибку."""
        mock_message = MockMessage("", user_id=22222)
        mock_message.text = None  # Симулируем отсутствие текста

        # Не должно упасть
        await handle_message(mock_message)

        # Не должно быть ответа
        assert len(mock_message.answers) == 0

        # Не должно быть сохранений в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 22222)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_no_from_user_does_not_crash(self):
        """Сообщение без from_user не вызывает ошибку."""
        mock_message = MockMessage("Продукты 100", user_id=33333)
        mock_message.from_user = None  # Симулируем отсутствие отправителя

        # Не должно упасть
        await handle_message(mock_message)

        # Не должно быть ответа
        assert len(mock_message.answers) == 0

    @pytest.mark.asyncio
    async def test_negative_amount_saves_correctly(self):
        """Отрицательная сумма (корректировка) сохраняется."""
        mock_message = MockMessage("корректировка -500.50", user_id=44444)

        await handle_message(mock_message)

        # Проверяем сохранение
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 44444)
            result = await session.execute(stmt)
            message = result.scalar_one()

            assert message.text == "корректировка -500.50"

        # Проверяем ответ
        assert len(mock_message.answers) == 1
        assert "1 расход успешно сохранено" in mock_message.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_decimal_with_comma_saves_correctly(self):
        """Decimal с запятой корректно сохраняется."""
        mock_message = MockMessage("Молоко 123,45", user_id=55555)

        await handle_message(mock_message)

        # Проверяем сохранение (запятая заменена на точку в тексте)
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 55555)
            result = await session.execute(stmt)
            message = result.scalar_one()

            # Парсер сохраняет с точкой
            assert message.text == "Молоко 123.45"

        assert len(mock_message.answers) == 1
