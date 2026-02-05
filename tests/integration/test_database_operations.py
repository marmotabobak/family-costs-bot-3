"""Расширенные интеграционные тесты для работы с БД."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, func, text

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.db.repositories.messages import save_message, delete_messages_by_ids
from bot.services.message_parser import parse_message


class TestFullMessageFlow:
    """Тесты полного E2E flow."""

    @pytest.mark.asyncio
    async def test_full_message_flow(self):
        """Полный flow: парсинг → сохранение → проверка в БД."""
        user_id = 123
        message_text = "Хлеб 30\nМолоко 50\nМясо 100"

        # 1. Парсинг
        result = parse_message(message_text)
        assert result is not None
        assert len(result.valid_lines) == 3

        # 2. Сохранение
        async with get_session() as session:
            for cost in result.valid_lines:
                await save_message(session, user_id, f"{cost.name} {cost.amount}")
            await session.commit()

        # 3. Проверка в БД
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.id)
            result_db = await session.execute(stmt)
            messages = result_db.scalars().all()

            assert len(messages) == 3
            assert messages[0].text == "Хлеб 30"
            assert messages[1].text == "Молоко 50"
            assert messages[2].text == "Мясо 100"


class TestTransactionBehavior:
    """Тесты поведения транзакций."""

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self):
        """При ошибке транзакция откатывается."""
        user_id = 456

        # Пытаемся сохранить с ошибкой
        try:
            async with get_session() as session:
                # Сохраняем первое сообщение (но еще не commit)
                message = Message(user_id=user_id, text="Test 1")
                session.add(message)

                # Имитируем ошибку перед commit
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Проверяем что ничего не сохранилось (rollback сработал)
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 0, "Rollback не сработал - данные остались в БД"

    @pytest.mark.asyncio
    async def test_save_message_with_commit(self):
        """После commit данные видны в другой сессии."""
        user_id = 789
        text = "Commit test"

        # Сохраняем в одной сессии
        async with get_session() as session:
            await save_message(session, user_id, text)
            await session.commit()

        # Читаем в другой сессии - данные должны быть видны
        async with get_session() as session:
            stmt = select(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            message = result.scalar_one()

            assert message.text == text


class TestMultipleMessages:
    """Тесты работы с множественными сообщениями."""

    @pytest.mark.asyncio
    async def test_save_multiple_messages(self):
        """Сохранение нескольких сообщений одним пользователем."""
        user_id = 999
        texts = [f"Message {i}" for i in range(10)]

        async with get_session() as session:
            for text in texts:
                await save_message(session, user_id, text)
            await session.commit()

        # Проверяем количество
        async with get_session() as session:
            stmt = select(func.count()).select_from(Message).where(Message.user_id == user_id)
            result = await session.execute(stmt)
            count = result.scalar()

            assert count == 10

    @pytest.mark.asyncio
    async def test_multiple_users_isolation(self):
        """Сообщения разных пользователей изолированы."""
        user1_id = 111
        user2_id = 222

        # Сохраняем для двух пользователей
        async with get_session() as session:
            await save_message(session, user1_id, "User 1 Message 1")
            await save_message(session, user1_id, "User 1 Message 2")
            await save_message(session, user2_id, "User 2 Message 1")
            await session.commit()

        # Проверяем что каждый видит только свои
        async with get_session() as session:
            stmt1 = select(func.count()).select_from(Message).where(Message.user_id == user1_id)
            result1 = await session.execute(stmt1)
            count1 = result1.scalar()

            stmt2 = select(func.count()).select_from(Message).where(Message.user_id == user2_id)
            result2 = await session.execute(stmt2)
            count2 = result2.scalar()

            assert count1 == 2
            assert count2 == 1


class TestDatabaseSchema:
    """Тесты схемы базы данных."""

    @pytest.mark.asyncio
    async def test_user_id_index_exists(self):
        """Проверяет что индекс на user_id создан."""
        async with get_session() as session:
            # Проверяем через information_schema PostgreSQL
            stmt = text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'messages'
                AND indexname = 'ix_messages_user_id'
            """)
            result = await session.execute(stmt)
            index = result.scalar()

            assert index is not None, "Индекс ix_messages_user_id не найден"

    @pytest.mark.asyncio
    async def test_primary_key_exists(self):
        """Проверяет что primary key на id создан."""
        async with get_session() as session:
            stmt = text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'messages'
                AND constraint_type = 'PRIMARY KEY'
            """)
            result = await session.execute(stmt)
            pk = result.scalar()

            assert pk is not None, "Primary key на messages.id не найден"


class TestTimestamps:
    """Тесты работы с временными метками."""

    @pytest.mark.asyncio
    async def test_created_at_has_timezone(self):
        """created_at сохраняется с timezone."""
        async with get_session() as session:
            message = await save_message(session, 555, "Timezone test")
            await session.commit()

            # Проверяем что timezone есть
            assert message.created_at.tzinfo is not None, "created_at не имеет timezone"

    @pytest.mark.asyncio
    async def test_created_at_is_recent(self):
        """created_at устанавливается в момент создания записи."""
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            message = await save_message(session, 666, "Timestamp test")
            await session.commit()

        # Проверяем что created_at близко к текущему времени (в пределах 5 секунд)
        # Используем abs() чтобы учесть возможную разницу часов Python/PostgreSQL
        time_diff = abs((now - message.created_at).total_seconds())
        assert time_diff < 5, f"created_at слишком далеко от текущего времени: {time_diff}s"

    @pytest.mark.asyncio
    async def test_messages_ordered_by_created_at(self):
        """Сообщения сохраняются в хронологическом порядке."""
        user_id = 777

        async with get_session() as session:
            msg1 = await save_message(session, user_id, "First")
            msg2 = await save_message(session, user_id, "Second")
            msg3 = await save_message(session, user_id, "Third")
            await session.commit()

        # Проверяем порядок по времени
        assert msg1.created_at <= msg2.created_at <= msg3.created_at


class TestConstraints:
    """Тесты проверки constraints на таблице messages."""

    @pytest.mark.asyncio
    async def test_user_id_constraint_rejects_zero(self):
        """CHECK constraint не позволяет сохранить user_id = 0."""
        from sqlalchemy.exc import IntegrityError

        async with get_session() as session:
            with pytest.raises(IntegrityError) as exc_info:
                await save_message(session, 0, "Invalid user_id")
                await session.commit()

            # Проверяем что ошибка связана с check constraint
            assert "check" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_user_id_constraint_rejects_negative(self):
        """CHECK constraint не позволяет сохранить отрицательный user_id."""
        from sqlalchemy.exc import IntegrityError

        async with get_session() as session:
            with pytest.raises(IntegrityError) as exc_info:
                await save_message(session, -1, "Negative user_id")
                await session.commit()

            # Проверяем что ошибка связана с check constraint
            assert "check" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_user_id_constraint_allows_positive(self):
        """CHECK constraint позволяет сохранить положительный user_id."""
        async with get_session() as session:
            message = await save_message(session, 123456789, "Valid user_id")
            await session.commit()

            assert message.id is not None
            assert message.user_id == 123456789

    @pytest.mark.asyncio
    async def test_check_constraint_exists_in_schema(self):
        """CHECK constraint на user_id существует в схеме БД."""
        async with get_session() as session:
            stmt = text("""
                SELECT constraint_name
                FROM information_schema.check_constraints
                WHERE constraint_name = 'messages_user_id_positive'
            """)
            result = await session.execute(stmt)
            constraint = result.scalar()

            assert constraint is not None, "CHECK constraint messages_user_id_positive не найден"


class TestDeleteMessages:
    @pytest.mark.asyncio
    async def test_delete_only_own_messages(self):
        user_id = 100
        other_user_id = 200

        async with get_session() as session:
            m1 = await save_message(session, user_id, "A")
            m2 = await save_message(session, user_id, "B")
            await save_message(session, other_user_id, "C")
            await session.commit()

        async with get_session() as session:
            deleted = await delete_messages_by_ids(
                session,
                [int(m1.id), int(m2.id)],
                user_id,
            )
            await session.commit()

        assert deleted == 2

        async with get_session() as session:
            stmt = select(Message)
            msgs = (await session.execute(stmt)).scalars().all()
            texts = [m.text for m in msgs]

            assert "C" in texts
            assert "A" not in texts
            assert "B" not in texts


class TestRepositoryFunctions:
    """Comprehensive tests for repository functions."""

    @pytest.mark.asyncio
    async def test_get_user_costs_stats_empty(self):
        """Статистика для пользователя без расходов."""
        from bot.db.repositories.messages import get_user_costs_stats

        async with get_session() as session:
            stats = await get_user_costs_stats(session, 99999)
            assert stats.count == 0
            assert stats.total_amount == Decimal("0")
            assert stats.first_date is None
            assert stats.last_date is None

    @pytest.mark.asyncio
    async def test_get_user_costs_stats_with_expenses(self):
        """Статистика для пользователя с расходами."""
        from bot.db.repositories.messages import get_user_costs_stats

        user_id = 10001
        async with get_session() as session:
            await save_message(session, user_id, "Test1 100")
            await save_message(session, user_id, "Test2 200")
            await save_message(session, user_id, "Test3 300")
            await session.commit()

            stats = await get_user_costs_stats(session, user_id)
            assert stats.count == 3
            assert stats.total_amount == Decimal("600")
            assert stats.first_date is not None
            assert stats.last_date is not None

    @pytest.mark.asyncio
    async def test_get_user_recent_costs(self):
        """Получение последних расходов."""
        from bot.db.repositories.messages import get_user_recent_costs

        user_id = 10002
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        async with get_session() as session:
            await save_message(session, user_id, "First 100", created_at=base_time)
            await save_message(session, user_id, "Second 200", created_at=base_time.replace(second=1))
            await save_message(session, user_id, "Third 300", created_at=base_time.replace(second=2))
            await session.commit()

            costs = await get_user_recent_costs(session, user_id, limit=2)
            assert len(costs) == 2
            assert costs[0][0] == "Third"
            assert costs[1][0] == "Second"

    @pytest.mark.asyncio
    async def test_get_user_available_months(self):
        """Получение доступных месяцев."""
        from bot.db.repositories.messages import get_user_available_months

        user_id = 10003
        async with get_session() as session:
            await save_message(
                session,
                user_id,
                "Test1 100",
                created_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
            )
            await save_message(
                session,
                user_id,
                "Test2 200",
                created_at=datetime(2024, 7, 15, tzinfo=timezone.utc),
            )
            await session.commit()

            months = await get_user_available_months(session, user_id)
            assert len(months) == 2
            assert (2024, 7) in months
            assert (2024, 6) in months

    @pytest.mark.asyncio
    async def test_get_user_costs_stats_with_invalid_text_format(self):
        """Статистика обрабатывает невалидный формат текста (пропускает)."""
        from bot.db.repositories.messages import get_user_costs_stats

        user_id = 10004
        async with get_session() as session:
            await save_message(session, user_id, "Valid 100")
            await save_message(session, user_id, "InvalidFormat")  # Нет суммы
            await save_message(session, user_id, "Another 200")
            await session.commit()

            stats = await get_user_costs_stats(session, user_id)
            assert stats.count == 3  # Все записи учитываются
            assert stats.total_amount == Decimal("300")  # Только валидные суммы

    @pytest.mark.asyncio
    async def test_get_user_recent_costs_with_invalid_text_format(self):
        """Последние расходы обрабатывают невалидный формат текста."""
        from bot.db.repositories.messages import get_user_recent_costs

        user_id = 10005
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        async with get_session() as session:
            await save_message(session, user_id, "Valid 100", created_at=base_time)
            await save_message(session, user_id, "InvalidFormat", created_at=base_time.replace(second=1))  # Нет суммы
            await save_message(session, user_id, "Another 200", created_at=base_time.replace(second=2))
            await session.commit()

            costs = await get_user_recent_costs(session, user_id, limit=10)
            # Должны быть только записи с валидным форматом
            assert len(costs) == 2
            assert costs[0][0] == "Another"
            assert costs[1][0] == "Valid"

    @pytest.mark.asyncio
    async def test_get_user_costs_by_month_with_invalid_text_format(self):
        """Расходы за месяц обрабатывают невалидный формат текста."""
        from bot.db.repositories.messages import get_user_costs_by_month

        user_id = 10006
        base_time = datetime(2024, 6, 15, tzinfo=timezone.utc)
        async with get_session() as session:
            await save_message(session, user_id, "Valid 100", created_at=base_time)
            await save_message(session, user_id, "InvalidFormat", created_at=base_time.replace(day=16))
            await save_message(session, user_id, "Another 200", created_at=base_time.replace(day=17))
            await session.commit()

            costs = await get_user_costs_by_month(session, user_id, 2024, 6)
            # Должны быть только записи с валидным форматом
            assert len(costs) == 2
            assert costs[0][0] == "Valid"
            assert costs[1][0] == "Another"
