"""E2E тесты для handle_message с реальной БД."""

import pytest
from sqlalchemy import select

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.routers.messages import handle_message, handle_undo


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

    async def set_data(self, data):
        """Устанавливает данные напрямую (заменяет существующие)."""
        self._data = data

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
        response_text = mock_message.answers[0]["text"]
        assert "Записано 1 расход" in response_text
        assert "Продукты: 100" in response_text

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
        response_text = mock_message.answers[0]["text"]
        assert "Записано 3 расхода" in response_text
        assert "Продукты: 100" in response_text
        assert "Вода: 50" in response_text
        assert "Хлеб: 30" in response_text

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
        response_text = mock_message.answers[0]["text"]
        assert "Записано 1 расход" in response_text
        assert "корректировка: -500.50" in response_text

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
    mock_message.answer = AsyncMock()  # Для handle_enter_past_month и других

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
        session_id = mock_state._data.get("confirmation_session_id")
        assert session_id is not None

        # Шаг 2: подтверждаем сохранение (используем session_id из state)
        mock_callback = create_mock_callback(user_id=user_id, data=f"confirm:{session_id}")

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
        assert "Записано 2 расхода" in edited_text
        assert "Продукты: 100" in edited_text
        assert "Вода: 50" in edited_text

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

        # Получаем session_id из state
        session_id = mock_state._data.get("confirmation_session_id")
        assert session_id is not None

        # Шаг 2: отменяем сохранение (используем session_id из state)
        mock_callback = create_mock_callback(user_id=user_id, data=f"cancel:{session_id}")

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


class TestUndoE2E:
    """E2E тесты отмены записей с реальной БД."""

    @pytest.mark.asyncio
    async def test_undo_deletes_records_from_db(self):
        """При отмене записи удаляются из БД."""
        user_id = 66600
        mock_message = MockMessage("Продукты 100\nВода 50", user_id=user_id)
        mock_state = MockState()

        # Шаг 1: сохраняем расходы
        await handle_message(mock_message, mock_state)

        # Получаем ID сохранённых записей из callback_data кнопки
        reply_markup = mock_message.answers[0]["kwargs"]["reply_markup"]
        undo_button = reply_markup.inline_keyboard[0][0]
        callback_data = undo_button.callback_data
        
        # Проверяем что записи в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages_before = result.scalars().all()
            assert len(messages_before) == 2

        # Шаг 2: отменяем
        mock_callback = create_mock_callback(user_id=user_id, data=callback_data)
        await handle_undo(mock_callback)

        # Проверяем что записи удалены из БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages_after = result.scalars().all()
            assert len(messages_after) == 0

        # Проверяем сообщение об отмене
        mock_callback.message.edit_text.assert_called_once()
        edited_text = mock_callback.message.edit_text.call_args[0][0]
        assert "Отменено" in edited_text
        assert "2" in edited_text

    @pytest.mark.asyncio
    async def test_undo_only_deletes_own_records(self):
        """Отмена удаляет только записи указанного пользователя."""
        user_id_1 = 66601
        user_id_2 = 66602

        # Пользователь 1 сохраняет расход
        mock_message_1 = MockMessage("Продукты 100", user_id=user_id_1)
        mock_state_1 = MockState()
        await handle_message(mock_message_1, mock_state_1)

        # Пользователь 2 сохраняет расход
        mock_message_2 = MockMessage("Вода 50", user_id=user_id_2)
        mock_state_2 = MockState()
        await handle_message(mock_message_2, mock_state_2)

        # Получаем ID записи пользователя 1
        reply_markup_1 = mock_message_1.answers[0]["kwargs"]["reply_markup"]
        callback_data_1 = reply_markup_1.inline_keyboard[0][0].callback_data

        # Пользователь 2 пытается отменить запись пользователя 1
        mock_callback = create_mock_callback(user_id=user_id_2, data=callback_data_1)
        await handle_undo(mock_callback)

        # Записи пользователя 1 не должны быть удалены (user_id не совпадает)
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id_1)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            assert len(messages) == 1  # Запись осталась

        # Записи пользователя 2 тоже должны остаться
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id_2)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            assert len(messages) == 1


class TestPastModeE2E:
    """E2E тесты режима ввода расходов за прошлый месяц с реальной БД."""

    @pytest.mark.asyncio
    async def test_past_mode_full_cycle(self):
        """
        Сценарий 1: включение режима → ввод → выключение → ввод на сегодня.
        
        1. Включаем режим прошлого (Июнь 2024)
        2. Вводим расход → записывается на 1 июня 2024
        3. Выключаем режим
        4. Вводим расход → записывается на сегодня
        """
        from datetime import datetime, timezone
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 88881
        mock_state = MockState()

        # Шаг 1: Включаем режим прошлого (Июнь 2024)
        mock_callback = create_mock_callback(user_id=user_id, data="enter_past_month:2024:6")
        await handle_enter_past_month(mock_callback, mock_state)

        # Проверяем что режим включён
        assert mock_state._data.get("past_mode_year") == 2024
        assert mock_state._data.get("past_mode_month") == 6

        # Шаг 2: Вводим расход в режиме прошлого
        mock_message1 = MockMessage("Продукты в прошлом 100", user_id=user_id)
        await handle_message(mock_message1, mock_state)

        # Проверяем что записалось на 1 июня 2024
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 1
            assert messages[0].text == "Продукты в прошлом 100"
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 6
            assert messages[0].created_at.day == 1

        # Шаг 3: Выключаем режим
        mock_callback2 = create_mock_callback(user_id=user_id, data="disable_past")
        await handle_disable_past(mock_callback2, mock_state)

        # Проверяем что режим выключен
        assert mock_state._data.get("past_mode_year") is None
        assert mock_state._data.get("past_mode_month") is None

        # Шаг 4: Вводим расход без режима прошлого
        mock_message2 = MockMessage("Продукты сегодня 200", user_id=user_id)
        await handle_message(mock_message2, mock_state)

        # Проверяем что записалось на сегодня
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 2
            # Второе сообщение должно быть записано на сегодня
            today = datetime.now(timezone.utc)
            assert messages[1].text == "Продукты сегодня 200"
            assert messages[1].created_at.year == today.year
            assert messages[1].created_at.month == today.month
            assert messages[1].created_at.day == today.day

    @pytest.mark.asyncio
    async def test_past_mode_switch_to_different_month(self):
        """
        Сценарий 2: переключение на другой месяц.
        
        1. Включаем режим прошлого (Июнь 2024)
        2. Вводим расход → записывается на 1 июня 2024
        3. Переключаемся на другой месяц (Март 2024)
        4. Вводим расход → записывается на 1 марта 2024
        5. Выключаем режим
        6. Вводим расход → записывается на сегодня
        """
        from datetime import datetime, timezone
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 88882
        mock_state = MockState()

        # Шаг 1: Включаем режим прошлого (Июнь 2024)
        mock_callback1 = create_mock_callback(user_id=user_id, data="enter_past_month:2024:6")
        await handle_enter_past_month(mock_callback1, mock_state)

        # Шаг 2: Вводим расход
        mock_message1 = MockMessage("Июньский расход 100", user_id=user_id)
        await handle_message(mock_message1, mock_state)

        # Шаг 3: Переключаемся на Март 2024
        mock_callback2 = create_mock_callback(user_id=user_id, data="enter_past_month:2024:3")
        await handle_enter_past_month(mock_callback2, mock_state)

        assert mock_state._data.get("past_mode_year") == 2024
        assert mock_state._data.get("past_mode_month") == 3

        # Шаг 4: Вводим расход
        mock_message2 = MockMessage("Мартовский расход 200", user_id=user_id)
        await handle_message(mock_message2, mock_state)

        # Шаг 5: Выключаем режим
        mock_callback3 = create_mock_callback(user_id=user_id, data="disable_past")
        await handle_disable_past(mock_callback3, mock_state)

        # Шаг 6: Вводим расход на сегодня
        mock_message3 = MockMessage("Сегодняшний расход 300", user_id=user_id)
        await handle_message(mock_message3, mock_state)

        # Проверяем все записи
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 3

            # Первый расход - Июнь 2024
            assert messages[0].text == "Июньский расход 100"
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 6
            assert messages[0].created_at.day == 1

            # Второй расход - Март 2024
            assert messages[1].text == "Мартовский расход 200"
            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 3
            assert messages[1].created_at.day == 1

            # Третий расход - сегодня
            today = datetime.now(timezone.utc)
            assert messages[2].text == "Сегодняшний расход 300"
            assert messages[2].created_at.year == today.year
            assert messages[2].created_at.month == today.month
            assert messages[2].created_at.day == today.day

    @pytest.mark.asyncio
    async def test_past_mode_reselect_same_month(self):
        """
        Сценарий 3: повторный выбор того же месяца.
        
        1. Включаем режим прошлого (Июнь 2024)
        2. Вводим расход → записывается на 1 июня 2024
        3. Повторно выбираем тот же месяц (Июнь 2024)
        4. Вводим расход → записывается на 1 июня 2024 (тот же месяц)
        5. Выключаем режим
        6. Вводим расход → записывается на сегодня
        """
        from datetime import datetime, timezone
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 88883
        mock_state = MockState()

        # Шаг 1: Включаем режим прошлого (Июнь 2024)
        mock_callback1 = create_mock_callback(user_id=user_id, data="enter_past_month:2024:6")
        await handle_enter_past_month(mock_callback1, mock_state)

        # Шаг 2: Вводим первый расход
        mock_message1 = MockMessage("Первый июньский 100", user_id=user_id)
        await handle_message(mock_message1, mock_state)

        # Шаг 3: Повторно выбираем тот же месяц (Июнь 2024)
        mock_callback2 = create_mock_callback(user_id=user_id, data="enter_past_month:2024:6")
        await handle_enter_past_month(mock_callback2, mock_state)

        # Режим всё ещё активен для того же месяца
        assert mock_state._data.get("past_mode_year") == 2024
        assert mock_state._data.get("past_mode_month") == 6

        # Шаг 4: Вводим второй расход
        mock_message2 = MockMessage("Второй июньский 200", user_id=user_id)
        await handle_message(mock_message2, mock_state)

        # Шаг 5: Выключаем режим
        mock_callback3 = create_mock_callback(user_id=user_id, data="disable_past")
        await handle_disable_past(mock_callback3, mock_state)

        # Шаг 6: Вводим расход на сегодня
        mock_message3 = MockMessage("Сегодняшний 300", user_id=user_id)
        await handle_message(mock_message3, mock_state)

        # Проверяем все записи
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 3

            # Первый расход - Июнь 2024
            assert messages[0].text == "Первый июньский 100"
            assert messages[0].created_at.year == 2024
            assert messages[0].created_at.month == 6
            assert messages[0].created_at.day == 1

            # Второй расход - тоже Июнь 2024 (тот же месяц!)
            assert messages[1].text == "Второй июньский 200"
            assert messages[1].created_at.year == 2024
            assert messages[1].created_at.month == 6
            assert messages[1].created_at.day == 1

            # Третий расход - сегодня
            today = datetime.now(timezone.utc)
            assert messages[2].text == "Сегодняшний 300"
            assert messages[2].created_at.year == today.year
            assert messages[2].created_at.month == today.month
            assert messages[2].created_at.day == today.day

    @pytest.mark.asyncio
    async def test_past_mode_multiple_costs_in_one_message(self):
        """Несколько расходов в одном сообщении записываются в режиме прошлого."""
        from bot.routers.menu import handle_enter_past_month

        user_id = 88884
        mock_state = MockState()

        # Включаем режим прошлого
        mock_callback = create_mock_callback(user_id=user_id, data="enter_past_month:2024:1")
        await handle_enter_past_month(mock_callback, mock_state)

        # Вводим несколько расходов одним сообщением
        mock_message = MockMessage("Продукты 100\nВода 50\nХлеб 30", user_id=user_id)
        await handle_message(mock_message, mock_state)

        # Проверяем что все записались на январь 2024
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 3
            for msg in messages:
                assert msg.created_at.year == 2024
                assert msg.created_at.month == 1
                assert msg.created_at.day == 1

    @pytest.mark.asyncio
    async def test_past_mode_enable_then_immediately_disable(self):
        """
        Сценарий: включение режима → сразу отключение → ввод на сегодня.
        
        1. Включаем режим прошлого (Июнь 2024)
        2. Сразу отключаем режим (без ввода расходов)
        3. Вводим расход → записывается на сегодня
        """
        from datetime import datetime, timezone
        from bot.routers.menu import handle_enter_past_month, handle_disable_past

        user_id = 88885
        mock_state = MockState()

        # Шаг 1: Включаем режим прошлого (Июнь 2024)
        mock_callback1 = create_mock_callback(user_id=user_id, data="enter_past_month:2024:6")
        await handle_enter_past_month(mock_callback1, mock_state)

        # Проверяем что режим включён
        assert mock_state._data.get("past_mode_year") == 2024
        assert mock_state._data.get("past_mode_month") == 6

        # Шаг 2: Сразу отключаем режим (без ввода расходов!)
        mock_callback2 = create_mock_callback(user_id=user_id, data="disable_past")
        await handle_disable_past(mock_callback2, mock_state)

        # Проверяем что режим выключен
        assert mock_state._data.get("past_mode_year") is None
        assert mock_state._data.get("past_mode_month") is None

        # Шаг 3: Вводим расход — должен записаться на сегодня
        mock_message = MockMessage("Продукты сегодня 100", user_id=user_id)
        await handle_message(mock_message, mock_state)

        # Проверяем что записалось на сегодня
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 1

            today = datetime.now(timezone.utc)
            assert messages[0].text == "Продукты сегодня 100"
            assert messages[0].created_at.year == today.year
            assert messages[0].created_at.month == today.month
            assert messages[0].created_at.day == today.day
