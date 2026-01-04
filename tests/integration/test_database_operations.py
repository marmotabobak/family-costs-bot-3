"""Расширенные интеграционные тесты для работы с БД."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select, func, text

from bot.db.dependencies import get_session
from bot.db.models import Message
from bot.db.repositories.messages import save_message
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
    async def test_save_message_commits_immediately(self):
        """save_message делает commit и данные сразу видны в другой сессии."""
        user_id = 789
        text = "Immediate commit test"

        # Сохраняем в одной сессии
        async with get_session() as session:
            await save_message(session, user_id, text)

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

            # Проверяем что timezone есть
            assert message.created_at.tzinfo is not None, "created_at не имеет timezone"

    @pytest.mark.asyncio
    async def test_created_at_is_recent(self):
        """created_at устанавливается в момент создания записи."""
        before = datetime.now(timezone.utc)

        async with get_session() as session:
            message = await save_message(session, 666, "Timestamp test")

        after = datetime.now(timezone.utc)

        # Проверяем что created_at между before и after
        assert before <= message.created_at <= after, "created_at не в ожидаемом диапазоне"

    @pytest.mark.asyncio
    async def test_messages_ordered_by_created_at(self):
        """Сообщения сохраняются в хронологическом порядке."""
        user_id = 777

        async with get_session() as session:
            msg1 = await save_message(session, user_id, "First")
            msg2 = await save_message(session, user_id, "Second")
            msg3 = await save_message(session, user_id, "Third")

        # Проверяем порядок по времени
        assert msg1.created_at <= msg2.created_at <= msg3.created_at

