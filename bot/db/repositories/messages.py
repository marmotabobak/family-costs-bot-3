from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Message


@dataclass
class UserCostsStats:
    """Статистика расходов пользователя."""

    total_amount: Decimal
    count: int
    first_date: datetime | None
    last_date: datetime | None


async def get_user_costs_stats(session: AsyncSession, user_id: int) -> UserCostsStats:
    """Возвращает статистику расходов пользователя."""
    result = await session.execute(
        select(Message.text, Message.created_at)
        .where(Message.user_id == user_id)
        .order_by(Message.created_at)
    )
    rows = result.all()

    if not rows:
        return UserCostsStats(
            total_amount=Decimal("0"),
            count=0,
            first_date=None,
            last_date=None,
        )

    total = Decimal("0")
    for row in rows:
        # Текст в формате "название сумма", берём последнее слово как сумму
        parts = row.text.rsplit(maxsplit=1)
        if len(parts) == 2:
            try:
                amount = Decimal(parts[1].replace(",", "."))
                total += amount
            except Exception:
                pass

    return UserCostsStats(
        total_amount=total,
        count=len(rows),
        first_date=rows[0].created_at,
        last_date=rows[-1].created_at,
    )


async def get_user_recent_costs(
    session: AsyncSession, user_id: int, limit: int = 10
) -> list[tuple[str, Decimal, datetime]]:
    """Возвращает последние расходы пользователя (название, сумма, дата)."""
    result = await session.execute(
        select(Message.text, Message.created_at)
        .where(Message.user_id == user_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = result.all()

    costs = []
    for row in rows:
        parts = row.text.rsplit(maxsplit=1)
        if len(parts) == 2:
            try:
                amount = Decimal(parts[1].replace(",", "."))
                costs.append((parts[0], amount, row.created_at))
            except Exception:
                pass

    return costs


async def get_unique_user_ids(session: AsyncSession) -> list[int]:
    """Возвращает список уникальных user_id из таблицы сообщений."""
    result = await session.execute(
        select(Message.user_id).distinct().order_by(Message.user_id)
    )
    return list(result.scalars().all())


async def get_user_costs_by_month(
    session: AsyncSession, user_id: int, year: int, month: int
) -> list[tuple[str, Decimal, datetime]]:
    """Возвращает расходы пользователя за конкретный месяц, отсортированные по дате."""
    from sqlalchemy import extract

    result = await session.execute(
        select(Message.text, Message.created_at)
        .where(Message.user_id == user_id)
        .where(extract("year", Message.created_at) == year)
        .where(extract("month", Message.created_at) == month)
        .order_by(Message.created_at)
    )
    rows = result.all()

    costs = []
    for row in rows:
        parts = row.text.rsplit(maxsplit=1)
        if len(parts) == 2:
            try:
                amount = Decimal(parts[1].replace(",", "."))
                costs.append((parts[0], amount, row.created_at))
            except Exception:
                pass

    return costs


async def get_user_available_months(
    session: AsyncSession, user_id: int
) -> list[tuple[int, int]]:
    """Возвращает список (year, month) для которых есть записи, отсортированный по убыванию."""
    from sqlalchemy import extract

    result = await session.execute(
        select(
            extract("year", Message.created_at).label("year"),
            extract("month", Message.created_at).label("month"),
        )
        .where(Message.user_id == user_id)
        .group_by("year", "month")
        .order_by(
            extract("year", Message.created_at).desc(),
            extract("month", Message.created_at).desc(),
        )
    )
    rows = result.all()

    return [(int(row.year), int(row.month)) for row in rows]


async def delete_messages_by_ids(
    session: AsyncSession,
    message_ids: list[int],
    user_id: int,
) -> int:
    """Удаляет сообщения по списку ID (только для указанного пользователя).
    
    Args:
        session: сессия БД
        message_ids: список ID сообщений для удаления
        user_id: ID пользователя (для безопасности - удаляем только свои)
    
    Returns:
        Количество удалённых записей
    """
    from sqlalchemy import delete
    from sqlalchemy.engine import Result
    
    result: Result[Any] = await session.execute(
        delete(Message)
        .where(Message.id.in_(message_ids))
        .where(Message.user_id == user_id)
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


async def save_message(
    session: AsyncSession,
    user_id: int,
    text: str,
    created_at: datetime | None = None,
) -> Message:
    """Создает объект сообщения без commit (для batch операций).
    
    Вызывающий код должен сам делать commit.
    Это позволяет сохранять несколько сообщений атомарно в одной транзакции.
    
    Args:
        session: сессия БД
        user_id: ID пользователя Telegram
        text: текст расхода
        created_at: опциональная дата создания (по умолчанию - текущее время)
    """
    message = Message(
        user_id=user_id,
        text=text,
    )
    
    # Если передана кастомная дата - устанавливаем её
    if created_at is not None:
        message.created_at = created_at  # type: ignore[assignment]

    session.add(message)
    await session.flush()  # Получаем id и created_at без commit
    await session.refresh(message)

    return message
