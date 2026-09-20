"""
E2E тесты для handle_message и связанных сценариев
без изменения messages.py.
"""

import pytest
from sqlalchemy import select

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.routers.messages import handle_message

pytestmark = pytest.mark.serial


# ======================================================
# Минимальные моки aiogram
# ======================================================


class MockUser:
    def __init__(self, user_id: int):
        self.id = user_id


class MockMessage:
    def __init__(self, text: str | None, user_id: int):
        self.text = text
        self.from_user = MockUser(user_id)
        self.answers: list[dict] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append({"text": text, "kwargs": kwargs})


class MockState:
    def __init__(self):
        self._state = None
        self._data = {}

    async def set_state(self, state):
        self._state = state

    async def get_state(self):
        return self._state

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def set_data(self, data: dict):
        self._data = data

    async def get_data(self):
        return self._data

    async def clear(self):
        self._state = None
        self._data = {}


def create_mock_callback(user_id: int, data: str):
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import CallbackQuery, Message as AiogramMessage

    msg = MagicMock(spec=AiogramMessage)
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()

    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = MockUser(user_id)
    cb.data = data
    cb.message = msg
    cb.answer = AsyncMock()

    return cb


# ======================================================
# handle_message — базовые сценарии
# ======================================================


class TestHandleMessageE2E:
    @pytest.mark.asyncio
    async def test_single_cost_saved(self):
        msg = MockMessage("Продукты 100", user_id=101)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            messages = (await session.execute(select(Message).where(Message.user_id == 101))).scalars().all()

            assert len(messages) == 1
            assert messages[0].text == "Продукты 100"

        assert len(msg.answers) == 1
        assert "Записано 1 расход" in msg.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_multiple_costs_saved(self):
        msg = MockMessage("Продукты 100\nВода 50\nХлеб 30", user_id=102)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            messages = (
                (await session.execute(select(Message).where(Message.user_id == 102).order_by(Message.id)))
                .scalars()
                .all()
            )

            assert [m.text for m in messages] == [
                "Продукты 100",
                "Вода 50",
                "Хлеб 30",
            ]

        assert "Записано 3 расхода" in msg.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_invalid_message_not_saved(self):
        msg = MockMessage("invalid message", user_id=103)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            messages = (await session.execute(select(Message).where(Message.user_id == 103))).scalars().all()

            assert messages == []

        assert len(msg.answers) == 2
        assert "Не удалось распарсить" in msg.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_no_text_safe(self):
        msg = MockMessage(None, user_id=104)
        state = MockState()

        await handle_message(msg, state)

        assert msg.answers == []

    @pytest.mark.asyncio
    async def test_negative_amount_allowed(self):
        msg = MockMessage("корректировка -500.50", user_id=105)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == 105))).scalar_one()

            assert message.text == "корректировка -500.50"


# ======================================================
# Edge Cases E2E Tests
# ======================================================


class TestEdgeCasesE2E:
    """E2E тесты для граничных случаев."""

    @pytest.mark.asyncio
    async def test_negative_amount_correction(self):
        """Отрицательная сумма для корректировки."""
        user_id = 401
        msg = MockMessage("корректировка -500.50", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == user_id))).scalar_one()

            assert "корректировка" in message.text
            assert "-500.50" in message.text

    @pytest.mark.asyncio
    async def test_zero_amount(self):
        """Нулевая сумма."""
        user_id = 402
        msg = MockMessage("бесплатно 0", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == user_id))).scalar_one()

            assert "бесплатно" in message.text
            assert "0" in message.text

    @pytest.mark.asyncio
    async def test_unicode_characters(self):
        """Unicode символы в сообщении."""
        user_id = 403
        msg = MockMessage("Продукты 🍎 100", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == user_id))).scalar_one()

            assert "🍎" in message.text

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Специальные символы в сообщении."""
        user_id = 404
        msg = MockMessage("заказ #123 @test 100", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == user_id))).scalar_one()

            assert "#123" in message.text
            assert "@test" in message.text

    @pytest.mark.asyncio
    async def test_very_large_amount(self):
        """Очень большая сумма."""
        user_id = 405
        msg = MockMessage("квартира 10000000.99", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (await session.execute(select(Message).where(Message.user_id == user_id))).scalar_one()

            assert "10000000.99" in message.text


    @pytest.mark.asyncio
    async def test_concurrent_saves(self):
        """Параллельное сохранение от одного пользователя."""
        user_id = 409
        state1 = MockState()
        state2 = MockState()

        msg1 = MockMessage("Расход1 100", user_id)
        msg2 = MockMessage("Расход2 200", user_id)

        # Сохраняем параллельно (в реальности последовательно, но быстро)
        await handle_message(msg1, state1)
        await handle_message(msg2, state2)

        async with get_session() as session:
            messages = (
                (await session.execute(select(Message).where(Message.user_id == user_id).order_by(Message.id)))
                .scalars()
                .all()
            )

            assert len(messages) == 2
            assert "Расход1" in messages[0].text
            assert "Расход2" in messages[1].text


# ======================================================
# Error Scenarios E2E Tests
# ======================================================


class TestErrorScenariosE2E:
    """E2E тесты для сценариев ошибок."""

    @pytest.mark.asyncio
    async def test_invalid_message_format(self):
        """Невалидный формат сообщения."""
        user_id = 501
        msg = MockMessage("invalid message", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            messages = (await session.execute(select(Message).where(Message.user_id == user_id))).scalars().all()

            assert len(messages) == 0

        assert len(msg.answers) == 2
        assert "Не удалось распарсить" in msg.answers[0]["text"]

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_lines(self):
        """Смешанные валидные и невалидные строки."""
        user_id = 502
        msg = MockMessage("Продукты 100\ninvalid\nВода 50", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        # Должно запросить подтверждение
        assert len(msg.answers) == 1
        assert "bad" in msg.answers[0]["text"].lower() or "не удалось" in msg.answers[0]["text"].lower()

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Пустое сообщение."""
        user_id = 503
        msg = MockMessage("", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            messages = (await session.execute(select(Message).where(Message.user_id == user_id))).scalars().all()

            assert len(messages) == 0

