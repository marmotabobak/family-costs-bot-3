"""
E2E тесты для handle_message и связанных сценариев
без изменения messages.py.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.routers.messages import CALLBACK_CONFIRM, CALLBACK_UNDO, handle_confirm, handle_message, handle_undo


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
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == 101)
                )
            ).scalars().all()

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
                await session.execute(
                    select(Message)
                    .where(Message.user_id == 102)
                    .order_by(Message.id)
                )
            ).scalars().all()

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
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == 103)
                )
            ).scalars().all()

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
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == 105)
                )
            ).scalar_one()

            assert message.text == "корректировка -500.50"


# ======================================================
# Undo — отмена записи
# ======================================================

class TestUndoE2E:

    @pytest.mark.asyncio
    async def test_undo_deletes_records(self):
        user_id = 201
        msg = MockMessage("Продукты 100\nВода 50", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        reply_markup = msg.answers[0]["kwargs"]["reply_markup"]
        undo_callback_data = reply_markup.inline_keyboard[0][0].callback_data

        callback = create_mock_callback(user_id=user_id, data=undo_callback_data)
        await handle_undo(callback, state)

        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalars().all()

            assert messages == []

    @pytest.mark.asyncio
    async def test_undo_does_not_delete_other_users(self):
        """Проверка безопасности: undo не удаляет записи других пользователей."""
        user1 = 202
        user2 = 203

        state1 = MockState()
        state2 = MockState()

        # пользователь 1 сохраняет расход
        msg1 = MockMessage("Продукты 100", user_id=user1)
        await handle_message(msg1, state1)

        # пользователь 2 сохраняет расход
        msg2 = MockMessage("Вода 50", user_id=user2)
        await handle_message(msg2, state2)

        # 🔒 контрольная точка ДО undo — запись пользователя 2 существует
        async with get_session() as session:
            msgs2_before = (
                await session.execute(
                    select(Message).where(Message.user_id == user2)
                )
            ).scalars().all()

            assert len(msgs2_before) == 1, "Запись пользователя 2 не сохранилась до undo"

        # пользователь 2 пытается undo по ID пользователя 1 (через state1)
        # Получаем ID сохраненных сообщений пользователя 1
        data1 = await state1.get_data()
        user1_ids = data1.get("last_saved_ids", [])

        # Создаем callback для пользователя 2 с ID пользователя 1
        callback = create_mock_callback(user_id=user2, data=CALLBACK_UNDO)
        # Устанавливаем в state2 ID пользователя 1 (попытка удалить чужие записи)
        await state2.update_data(last_saved_ids=user1_ids)
        await handle_undo(callback, state2)

        # 🔒 контрольная точка ПОСЛЕ undo — запись пользователя 2 осталась
        async with get_session() as session:
            msgs2_after = (
                await session.execute(
                    select(Message).where(Message.user_id == user2)
                )
            ).scalars().all()

            assert len(msgs2_after) == 1, "Запись пользователя 2 была удалена (нарушение безопасности)"

        # Проверяем что запись пользователя 1 тоже осталась (не была удалена пользователем 2)
        async with get_session() as session:
            msgs1_after = (
                await session.execute(
                    select(Message).where(Message.user_id == user1)
                )
            ).scalars().all()

            assert len(msgs1_after) == 1, "Запись пользователя 1 была удалена"


# ======================================================
# Past mode — ключевой сценарий
# ======================================================

class TestPastModeE2E:

    @pytest.mark.asyncio
    async def test_past_mode_basic_flow(self):
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 301
        state = MockState()

        cb1 = create_mock_callback(user_id, "enter_past_month:2024:6")
        await handle_enter_past_month(cb1, state)

        msg1 = MockMessage("Прошлый расход 100", user_id)
        await handle_message(msg1, state)

        cb2 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb2, state)

        msg2 = MockMessage("Сегодняшний расход 200", user_id)
        await handle_message(msg2, state)

        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 2

            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 6
            assert messages[0].created_at.day == 1

            today = datetime.now(timezone.utc)
            assert messages[1].created_at.date() == today.date()


# ======================================================
# Comprehensive Past Mode E2E Scenarios (E2E-PM-1 through E2E-PM-12)
# ======================================================

class TestPastModeComplexE2E:
    """Comprehensive E2E tests for past mode complex scenarios."""

    @pytest.mark.asyncio
    async def test_e2e_pm_1_multiple_expenses_with_past_mode_enabled_disabled_multiple_times(self):
        """
        E2E-PM-1: Multiple expenses with past mode enabled/disabled multiple times.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 5001
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send 2 expenses in past mode
        msg1 = MockMessage("Продукты 100", user_id)
        await handle_message(msg1, state)
        msg2 = MockMessage("Вода 50", user_id)
        await handle_message(msg2, state)

        # Disable past mode
        cb2 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb2, state)

        # Send 1 expense with current date
        msg3 = MockMessage("Хлеб 30", user_id)
        await handle_message(msg3, state)

        # Enable past mode for February 2024 (different month)
        cb3 = create_mock_callback(user_id, "enter_past_month:2024:2")
        await handle_enter_past_month(cb3, state)

        # Send 2 expenses in past mode
        msg4 = MockMessage("Мясо 200", user_id)
        await handle_message(msg4, state)
        msg5 = MockMessage("Сыр 80", user_id)
        await handle_message(msg5, state)

        # Disable past mode
        cb4 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb4, state)

        # Send 1 expense with current date
        msg6 = MockMessage("Молоко 40", user_id)
        await handle_message(msg6, state)

        # Verify all expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 6

            # Expenses 1-2: March 2024
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 3
            assert messages[0].created_at.day == 1
            assert messages[0].text == "Продукты 100"

            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 3
            assert messages[1].created_at.day == 1
            assert messages[1].text == "Вода 50"

            # Expense 3: Current date
            today = datetime.now(timezone.utc)
            assert messages[2].created_at.date() == today.date()
            assert messages[2].text == "Хлеб 30"

            # Expenses 4-5: February 2024
            assert messages[3].created_at.year == 2024
            assert messages[3].created_at.month == 2
            assert messages[3].created_at.day == 1
            assert messages[3].text == "Мясо 200"

            assert messages[4].created_at.year == 2024
            assert messages[4].created_at.month == 2
            assert messages[4].created_at.day == 1
            assert messages[4].text == "Сыр 80"

            # Expense 6: Current date
            assert messages[5].created_at.date() == today.date()
            assert messages[5].text == "Молоко 40"

    @pytest.mark.asyncio
    async def test_e2e_pm_2_switching_between_different_past_months(self):
        """
        E2E-PM-2: Switching between different past months.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5002
        state = MockState()

        # Enable past mode for January 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:1")
        await handle_enter_past_month(cb1, state)

        msg1 = MockMessage("Расход1 100", user_id)
        await handle_message(msg1, state)

        # Switch to December 2023 (without disabling)
        cb2 = create_mock_callback(user_id, "enter_past_month:2023:12")
        await handle_enter_past_month(cb2, state)

        msg2 = MockMessage("Расход2 200", user_id)
        await handle_message(msg2, state)

        # Switch to November 2023
        cb3 = create_mock_callback(user_id, "enter_past_month:2023:11")
        await handle_enter_past_month(cb3, state)

        msg3 = MockMessage("Расход3 300", user_id)
        await handle_message(msg3, state)

        # Verify all expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 3

            # Expense 1: January 2024
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 1
            assert messages[0].created_at.day == 1

            # Expense 2: December 2023
            assert messages[1].created_at.year == 2023
            assert messages[1].created_at.month == 12
            assert messages[1].created_at.day == 1

            # Expense 3: November 2023
            assert messages[2].created_at.year == 2023
            assert messages[2].created_at.month == 11
            assert messages[2].created_at.day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_3_past_mode_with_confirmation_flow(self):
        """
        E2E-PM-3: Past mode with confirmation flow (mixed valid/invalid).
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5003
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send message with mixed valid/invalid lines
        msg = MockMessage("Продукты 100\ninvalid line without amount\nВода 50", user_id)
        await handle_message(msg, state)

        # Verify confirmation was requested
        assert len(msg.answers) == 1
        assert "Продукты" in msg.answers[0]["text"]
        assert "Вода" in msg.answers[0]["text"]
        assert "invalid" in msg.answers[0]["text"].lower()

        # Confirm
        callback = create_mock_callback(user_id, CALLBACK_CONFIRM)
        await handle_confirm(callback, state)

        # Send another expense (past mode should still be active)
        msg2 = MockMessage("Хлеб 30", user_id)
        await handle_message(msg2, state)

        # Verify expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 3  # Only valid lines saved

            # All should have past date (March 2024)
            for msg in messages:
                assert msg.created_at.year == 2024
                assert msg.created_at.month == 3
                assert msg.created_at.day == 1

            assert messages[0].text == "Продукты 100"
            assert messages[1].text == "Вода 50"
            assert messages[2].text == "Хлеб 30"

    @pytest.mark.asyncio
    async def test_e2e_pm_4_past_mode_with_undo_operations(self):
        """
        E2E-PM-4: Past mode with undo operations.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5004
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send 2 expenses
        msg1 = MockMessage("Продукты 100", user_id)
        await handle_message(msg1, state)
        msg2 = MockMessage("Вода 50", user_id)
        await handle_message(msg2, state)

        # Undo last expense
        callback = create_mock_callback(user_id, CALLBACK_UNDO)
        await handle_undo(callback, state)

        # Verify past mode still active - send new expense
        msg3 = MockMessage("Хлеб 30", user_id)
        await handle_message(msg3, state)

        # Verify expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 2  # One was undone

            # Both should have past date (past mode still active)
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 3
            assert messages[0].created_at.day == 1
            assert messages[0].text == "Продукты 100"

            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 3
            assert messages[1].created_at.day == 1
            assert messages[1].text == "Хлеб 30"

    @pytest.mark.asyncio
    async def test_e2e_pm_5_multiple_expenses_past_to_current_to_past(self):
        """
        E2E-PM-5: Multiple expenses in past mode → Switch to current → Back to past.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 5005
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send 2 expenses in past mode
        msg1 = MockMessage("Продукты 100", user_id)
        await handle_message(msg1, state)
        msg2 = MockMessage("Вода 50", user_id)
        await handle_message(msg2, state)

        # Disable past mode
        cb2 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb2, state)

        # Send 2 expenses with current date
        msg3 = MockMessage("Хлеб 30", user_id)
        await handle_message(msg3, state)
        msg4 = MockMessage("Молоко 40", user_id)
        await handle_message(msg4, state)

        # Enable past mode for February 2024 (different month)
        cb3 = create_mock_callback(user_id, "enter_past_month:2024:2")
        await handle_enter_past_month(cb3, state)

        # Send 2 expenses in past mode
        msg5 = MockMessage("Мясо 200", user_id)
        await handle_message(msg5, state)
        msg6 = MockMessage("Сыр 80", user_id)
        await handle_message(msg6, state)

        # Verify all expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 6

            # Expenses 1-2: March 2024
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 3
            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 3

            # Expenses 3-4: Current date
            today = datetime.now(timezone.utc)
            assert messages[2].created_at.date() == today.date()
            assert messages[3].created_at.date() == today.date()

            # Expenses 5-6: February 2024
            assert messages[4].created_at.year == 2024
            assert messages[4].created_at.month == 2
            assert messages[5].created_at.year == 2024
            assert messages[5].created_at.month == 2

    @pytest.mark.asyncio
    async def test_e2e_pm_6_complex_state_changes(self):
        """
        E2E-PM-6: Complex state changes - Enable → Multiple expenses → Disable → More expenses → Re-enable different month.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 5006
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send 3 expenses in one message
        msg1 = MockMessage("Продукты 100\nВода 50\nХлеб 30", user_id)
        await handle_message(msg1, state)

        # Disable past mode
        cb2 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb2, state)

        # Send 1 expense with current date
        msg2 = MockMessage("Молоко 40", user_id)
        await handle_message(msg2, state)

        # Enable past mode for January 2024 (different month)
        cb3 = create_mock_callback(user_id, "enter_past_month:2024:1")
        await handle_enter_past_month(cb3, state)

        # Send 2 expenses in past mode
        msg3 = MockMessage("Мясо 200\nСыр 80", user_id)
        await handle_message(msg3, state)

        # Verify all expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 6

            # Expenses 1-3: March 2024
            for i in range(3):
                assert messages[i].created_at.year == 2024
                assert messages[i].created_at.month == 3
                assert messages[i].created_at.day == 1

            # Expense 4: Current date
            today = datetime.now(timezone.utc)
            assert messages[3].created_at.date() == today.date()

            # Expenses 5-6: January 2024
            for i in range(4, 6):
                assert messages[i].created_at.year == 2024
                assert messages[i].created_at.month == 1
                assert messages[i].created_at.day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_7_past_mode_with_multiple_users_isolation(self):
        """
        E2E-PM-7: Past mode with multiple users (isolation).
        Priority: HIGH
        """
        from bot.routers.menu import handle_enter_past_month

        user_a = 5007
        user_b = 5008
        state_a = MockState()
        state_b = MockState()

        # User A enables past mode for March 2024
        cb_a1 = create_mock_callback(user_a, "enter_past_month:2024:3")
        await handle_enter_past_month(cb_a1, state_a)

        # User A sends expense
        msg_a1 = MockMessage("Продукты 100", user_a)
        await handle_message(msg_a1, state_a)

        # User B sends expense (no past mode)
        msg_b1 = MockMessage("Транспорт 50", user_b)
        await handle_message(msg_b1, state_b)

        # User B enables past mode for February 2024
        cb_b1 = create_mock_callback(user_b, "enter_past_month:2024:2")
        await handle_enter_past_month(cb_b1, state_b)

        # User B sends expense
        msg_b2 = MockMessage("Обед 80", user_b)
        await handle_message(msg_b2, state_b)

        # User A sends expense (past mode still active for March)
        msg_a2 = MockMessage("Вода 30", user_a)
        await handle_message(msg_a2, state_a)

        # Verify User A's expenses
        async with get_session() as session:
            messages_a = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_a)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages_a) == 2
            # Both should have March 2024 date
            for msg in messages_a:
                assert msg.created_at.year == 2024
                assert msg.created_at.month == 3
                assert msg.created_at.day == 1

        # Verify User B's expenses
        async with get_session() as session:
            messages_b = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_b)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages_b) == 2

            # First expense: current date
            today = datetime.now(timezone.utc)
            assert messages_b[0].created_at.date() == today.date()

            # Second expense: February 2024
            assert messages_b[1].created_at.year == 2024
            assert messages_b[1].created_at.month == 2
            assert messages_b[1].created_at.day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_8_past_mode_undo_past_mode_still_active(self):
        """
        E2E-PM-8: Past mode → Undo → Past mode still active → New expense.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5009
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send expense
        msg1 = MockMessage("Продукты 100", user_id)
        await handle_message(msg1, state)

        # Undo
        callback = create_mock_callback(user_id, CALLBACK_UNDO)
        await handle_undo(callback, state)

        # Verify past mode still active - send new expense
        msg2 = MockMessage("Вода 50", user_id)
        await handle_message(msg2, state)

        # Verify expense
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 1  # First was undone
            assert messages[0].text == "Вода 50"
            # Should have past date (past mode still active)
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 3
            assert messages[0].created_at.day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_9_past_mode_view_report_add_more_view_again(self):
        """
        E2E-PM-9: Past mode → View report → Add more past expenses → View again.
        Priority: HIGH
        """
        from bot.routers.menu import handle_enter_past_month
        from bot.db.repositories.messages import get_user_costs_by_month

        user_id = 5010
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send expense
        msg1 = MockMessage("Продукты 100", user_id)
        await handle_message(msg1, state)

        # View report (simulate via repository)
        async with get_session() as session:
            costs1 = await get_user_costs_by_month(session, user_id, 2024, 3)
            assert len(costs1) == 1

        # Send 2 more expenses (past mode should still be active)
        msg2 = MockMessage("Вода 50\nХлеб 30", user_id)
        await handle_message(msg2, state)

        # View report again
        async with get_session() as session:
            costs2 = await get_user_costs_by_month(session, user_id, 2024, 3)
            assert len(costs2) == 3

            # Verify all have correct dates
            for cost in costs2:
                assert cost[2].year == 2024
                assert cost[2].month == 3
                assert cost[2].day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_10_past_mode_january_switch_to_december_previous_year(self):
        """
        E2E-PM-10: Past mode January → Switch to December previous year → Multiple expenses.
        Priority: HIGH
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5011
        state = MockState()

        # Enable past mode for January 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:1")
        await handle_enter_past_month(cb1, state)

        msg1 = MockMessage("Расход1 100", user_id)
        await handle_message(msg1, state)

        # Switch to December 2023 (previous year)
        cb2 = create_mock_callback(user_id, "enter_past_month:2023:12")
        await handle_enter_past_month(cb2, state)

        msg2 = MockMessage("Расход2 200\nРасход3 300", user_id)
        await handle_message(msg2, state)

        # Verify expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 3

            # Expense 1: January 2024
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 1
            assert messages[0].created_at.day == 1

            # Expenses 2-3: December 2023
            assert messages[1].created_at.year == 2023
            assert messages[1].created_at.month == 12
            assert messages[1].created_at.day == 1

            assert messages[2].created_at.year == 2023
            assert messages[2].created_at.month == 12
            assert messages[2].created_at.day == 1

    @pytest.mark.asyncio
    async def test_e2e_pm_11_alternating_pattern_current_past_current_past_different_month(self):
        """
        E2E-PM-11: Alternating pattern - Current → Past → Current → Past different month.
        Priority: HIGH
        """
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 5012
        state = MockState()

        # Current expense
        msg1 = MockMessage("Текущий1 100", user_id)
        await handle_message(msg1, state)

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Past expense
        msg2 = MockMessage("Прошлый1 200", user_id)
        await handle_message(msg2, state)

        # Disable past mode
        cb2 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb2, state)

        # Current expense
        msg3 = MockMessage("Текущий2 150", user_id)
        await handle_message(msg3, state)

        # Enable past mode for February 2024 (different month)
        cb3 = create_mock_callback(user_id, "enter_past_month:2024:2")
        await handle_enter_past_month(cb3, state)

        # Past expense
        msg4 = MockMessage("Прошлый2 250", user_id)
        await handle_message(msg4, state)

        # Disable past mode
        cb4 = create_mock_callback(user_id, "disable_past")
        await handle_disable_past(cb4, state)

        # Current expense
        msg5 = MockMessage("Текущий3 180", user_id)
        await handle_message(msg5, state)

        # Verify all expenses
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages) == 5

            today = datetime.now(timezone.utc)

            # Expense 1: Current date
            assert messages[0].created_at.date() == today.date()
            assert messages[0].text == "Текущий1 100"

            # Expense 2: March 2024
            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 3
            assert messages[1].created_at.day == 1
            assert messages[1].text == "Прошлый1 200"

            # Expense 3: Current date
            assert messages[2].created_at.date() == today.date()
            assert messages[2].text == "Текущий2 150"

            # Expense 4: February 2024
            assert messages[3].created_at.year == 2024
            assert messages[3].created_at.month == 2
            assert messages[3].created_at.day == 1
            assert messages[3].text == "Прошлый2 250"

            # Expense 5: Current date
            assert messages[4].created_at.date() == today.date()
            assert messages[4].text == "Текущий3 180"

    @pytest.mark.asyncio
    async def test_e2e_pm_12_past_mode_confirmation_confirm_past_date_undo_past_mode_still_active(self):
        """
        E2E-PM-12: Past mode → Confirmation needed → Confirm → Past date used → Undo → Past mode still active.
        Priority: CRITICAL
        """
        from bot.routers.menu import handle_enter_past_month

        user_id = 5013
        state = MockState()

        # Enable past mode for March 2024
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:3")
        await handle_enter_past_month(cb1, state)

        # Send message with mixed valid/invalid lines
        msg1 = MockMessage("Продукты 100\ninvalid line\nВода 50", user_id)
        await handle_message(msg1, state)

        # Verify confirmation was requested
        assert len(msg1.answers) == 1
        assert "Продукты" in msg1.answers[0]["text"]
        assert "Вода" in msg1.answers[0]["text"]

        # Confirm
        callback = create_mock_callback(user_id, CALLBACK_CONFIRM)
        await handle_confirm(callback, state)

        # Verify expenses were saved with past date
        async with get_session() as session:
            messages_before_undo = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

            assert len(messages_before_undo) == 2
            for msg in messages_before_undo:
                assert msg.created_at.year == 2024
                assert msg.created_at.month == 3
                assert msg.created_at.day == 1

        # Undo
        undo_callback = create_mock_callback(user_id, CALLBACK_UNDO)
        await handle_undo(undo_callback, state)

        # Verify expenses deleted
        async with get_session() as session:
            messages_after_undo = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                )
            ).scalars().all()

            assert len(messages_after_undo) == 0

        # Verify past mode still active - send new expense
        msg2 = MockMessage("Хлеб 30", user_id)
        await handle_message(msg2, state)

        # Verify new expense has past date
        async with get_session() as session:
            messages_final = (
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                )
            ).scalars().all()

            assert len(messages_final) == 1
            assert messages_final[0].text == "Хлеб 30"
            assert messages_final[0].created_at.year == 2024
            assert messages_final[0].created_at.month == 3
            assert messages_final[0].created_at.day == 1


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
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

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
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

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
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

            assert "🍎" in message.text

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Специальные символы в сообщении."""
        user_id = 404
        msg = MockMessage("заказ #123 @test 100", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        async with get_session() as session:
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

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
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

            assert "10000000.99" in message.text

    @pytest.mark.asyncio
    async def test_multiple_undo_attempts(self):
        """Множественные попытки undo."""
        user_id = 406
        msg = MockMessage("Продукты 100", user_id=user_id)
        state = MockState()

        await handle_message(msg, state)

        # Первый undo
        callback1 = create_mock_callback(user_id=user_id, data=CALLBACK_UNDO)
        await handle_undo(callback1, state)

        # Второй undo (нечего отменять)
        callback2 = create_mock_callback(user_id=user_id, data=CALLBACK_UNDO)
        await handle_undo(callback2, state)

        # Проверяем что после первого undo запись удалена
        async with get_session() as session:
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalars().all()

            assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_past_mode_leap_year(self):
        """Past mode для високосного года."""
        from bot.routers.menu import handle_enter_past_month

        user_id = 407
        state = MockState()

        # Включаем past mode для февраля 2024 (високосный год)
        cb1 = create_mock_callback(user_id, "enter_past_month:2024:2")
        await handle_enter_past_month(cb1, state)

        msg = MockMessage("Расход 100", user_id)
        await handle_message(msg, state)

        async with get_session() as session:
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

            assert message.created_at.year == 2024
            assert message.created_at.month == 2
            assert message.created_at.day == 1

    @pytest.mark.asyncio
    async def test_past_mode_year_boundary(self):
        """Past mode для граничного года."""
        from bot.routers.menu import handle_enter_past_month

        user_id = 408
        state = MockState()

        # Включаем past mode для января предыдущего года
        now = datetime.now(timezone.utc)
        prev_year = now.year - 1
        cb1 = create_mock_callback(user_id, f"enter_past_month:{prev_year}:1")
        await handle_enter_past_month(cb1, state)

        msg = MockMessage("Расход 100", user_id)
        await handle_message(msg, state)

        async with get_session() as session:
            message = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalar_one()

            assert message.created_at.year == prev_year
            assert message.created_at.month == 1

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
                await session.execute(
                    select(Message)
                    .where(Message.user_id == user_id)
                    .order_by(Message.id)
                )
            ).scalars().all()

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
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalars().all()

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
            messages = (
                await session.execute(
                    select(Message).where(Message.user_id == user_id)
                )
            ).scalars().all()

            assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_undo_without_saved_ids(self):
        """Undo без сохраненных ID."""
        user_id = 504
        state = MockState()
        # State пустой, нет last_saved_ids

        callback = create_mock_callback(user_id=user_id, data=CALLBACK_UNDO)
        await handle_undo(callback, state)

        # Должно показать сообщение об ошибке
        assert callback.answer.called
        # Проверяем что был вызван с show_alert=True или с текстом ошибки
        call_args = callback.answer.call_args
        assert call_args is not None
