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


class MockState:
    """Мок для FSMContext."""

    def __init__(self):
        self._state = None
        self._data = {}

    async def set_state(self, state):
        self._state = state

    async def get_state(self):
        return self._state

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def get_data(self):
        return self._data

    async def clear(self):
        self._state = None
        self._data = {}


class TestHandleMessageE2E:
    """E2E тесты обработчика сообщений с реальной БД."""

    @pytest.mark.asyncio
    async def test_successful_single_cost_saves_to_db(self):
        """Успешное сохранение одного расхода в реальную БД."""
        mock_message = MockMessage("Продукты 100", user_id=12345)
        mock_state = MockState()

        await handle_message(mock_message, mock_state)

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
        mock_state = MockState()

        await handle_message(mock_message, mock_state)

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
        mock_state = MockState()

        await handle_message(mock_message, mock_state)

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
    async def test_no_text_does_not_crash(self):
        """Сообщение без текста не вызывает ошибку."""
        mock_message = MockMessage("", user_id=22222)
        mock_message.text = None  # Симулируем отсутствие текста
        mock_state = MockState()

        # Не должно упасть
        await handle_message(mock_message, mock_state)

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
        mock_state = MockState()

        # Не должно упасть
        await handle_message(mock_message, mock_state)

        # Не должно быть ответа
        assert len(mock_message.answers) == 0

    @pytest.mark.asyncio
    async def test_negative_amount_saves_correctly(self):
        """Отрицательная сумма (корректировка) сохраняется."""
        mock_message = MockMessage("корректировка -500.50", user_id=44444)
        mock_state = MockState()

        await handle_message(mock_message, mock_state)

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
        mock_state = MockState()

        await handle_message(mock_message, mock_state)

        # Проверяем сохранение (запятая заменена на точку в тексте)
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == 55555)
            result = await session.execute(stmt)
            message = result.scalar_one()

            # Парсер сохраняет с точкой
            assert message.text == "Молоко 123.45"

        assert len(mock_message.answers) == 1


def create_mock_callback(user_id: int, data: str):
    """Создаёт мок CallbackQuery с правильными типами."""
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import CallbackQuery, Message as AiogramMessage

    mock_message = MagicMock(spec=AiogramMessage)
    mock_message.edit_text = AsyncMock()

    mock_callback = MagicMock(spec=CallbackQuery)
    mock_callback.from_user = MockUser(user_id)
    mock_callback.data = data
    mock_callback.message = mock_message
    mock_callback.answer = AsyncMock()

    return mock_callback


class TestConfirmationE2E:
    """E2E тесты подтверждения/отмены записи с реальной БД."""

    @pytest.mark.asyncio
    async def test_confirm_saves_valid_costs_to_db(self):
        """При подтверждении валидные расходы записываются в БД."""
        from bot.routers.messages import handle_confirm_save

        user_id = 66666
        mock_message = MockMessage(
            "Продукты 100\ninvalid line\nВода 50",
            user_id=user_id,
        )
        mock_state = MockState()

        # Шаг 1: отправляем сообщение с невалидными строками
        await handle_message(mock_message, mock_state)

        # Проверяем что ничего не сохранено до подтверждения
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            assert len(messages) == 0

        # Проверяем что запрошено подтверждение с правильным содержимым
        assert len(mock_message.answers) == 1
        response = mock_message.answers[0]["text"]
        assert "Не удалось распознать строки" in response
        assert "invalid line" in response
        assert "Записать" in response
        assert "reply_markup" in mock_message.answers[0]["kwargs"]

        # Проверяем что state установлен корректно
        assert mock_state._state is not None
        assert len(mock_state._data.get("valid_costs", [])) == 2

        # Шаг 2: подтверждаем сохранение
        mock_callback = create_mock_callback(user_id=user_id, data="confirm_save")

        await handle_confirm_save(mock_callback, mock_state)

        # Проверяем что валидные расходы сохранены в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 2
            assert messages[0].text == "Продукты 100"
            assert messages[1].text == "Вода 50"

        # Проверяем ответ
        mock_callback.answer.assert_called_once()
        mock_callback.message.edit_text.assert_called_once()
        edited_text = mock_callback.message.edit_text.call_args[0][0]
        assert "успешно сохранено" in edited_text

    @pytest.mark.asyncio
    async def test_cancel_does_not_save_to_db(self):
        """При отмене ничего не записывается в БД."""
        from bot.routers.messages import handle_cancel_save

        user_id = 77777
        mock_message = MockMessage(
            "Продукты 100\ninvalid line\nВода 50",
            user_id=user_id,
        )
        mock_state = MockState()

        # Шаг 1: отправляем сообщение с невалидными строками
        await handle_message(mock_message, mock_state)

        # Проверяем что ничего не сохранено
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            assert len(messages) == 0

        # Шаг 2: отменяем сохранение
        mock_callback = create_mock_callback(user_id=user_id, data="cancel_save")

        await handle_cancel_save(mock_callback, mock_state)

        # Проверяем что ничего не сохранено в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 0

        # Проверяем что state очищен
        assert mock_state._state is None
        assert mock_state._data == {}

        # Проверяем ответ
        mock_callback.answer.assert_called_once()
        mock_callback.message.edit_text.assert_called_once()
        edited_text = mock_callback.message.edit_text.call_args[0][0]
        assert "отменено" in edited_text.lower()
