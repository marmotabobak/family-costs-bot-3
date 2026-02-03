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


@dataclass
class PaginatedCosts:
    """Результат пагинированного запроса расходов."""

    items: list[Message]
    total: int
    page: int
    per_page: int
    total_pages: int


async def get_all_costs_paginated(
    session: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> PaginatedCosts:
    """Возвращает все расходы с пагинацией (для веб-интерфейса)."""
    from sqlalchemy import func

    # Получаем общее количество записей
    count_result = await session.execute(select(func.count(Message.id)))
    total = count_result.scalar() or 0

    # Вычисляем параметры пагинации
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    # Получаем записи
    result = await session.execute(
        select(Message)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = list(result.scalars().all())

    return PaginatedCosts(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


async def get_message_by_id(session: AsyncSession, message_id: int) -> Message | None:
    """Возвращает сообщение по ID."""
    result = await session.execute(select(Message).where(Message.id == message_id))
    return result.scalar_one_or_none()


async def update_message(
    session: AsyncSession,
    message_id: int,
    text: str,
    user_id: int | None = None,
    created_at: datetime | None = None,
) -> Message | None:
    """Обновляет сообщение по ID.

    Args:
        session: сессия БД
        message_id: ID сообщения
        text: новый текст
        user_id: новый user_id (опционально)
        created_at: новая дата (опционально)

    Returns:
        Обновленное сообщение или None если не найдено
    """
    message = await get_message_by_id(session, message_id)
    if message is None:
        return None

    message.text = text  # type: ignore[assignment]
    if user_id is not None:
        message.user_id = user_id  # type: ignore[assignment]
    if created_at is not None:
        message.created_at = created_at  # type: ignore[assignment]

    await session.flush()
    await session.refresh(message)
    return message


async def delete_message_by_id(session: AsyncSession, message_id: int) -> bool:
    """Удаляет сообщение по ID.

    Returns:
        True если удалено, False если не найдено
    """
    from sqlalchemy import delete
    from sqlalchemy.engine import Result

    result: Result[Any] = await session.execute(
        delete(Message).where(Message.id == message_id)
    )
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]
