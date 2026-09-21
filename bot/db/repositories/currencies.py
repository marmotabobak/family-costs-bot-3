"""Async repository for Currency and ExchangeRate CRUD operations.

Design invariants enforced here (in addition to DB constraints):

1. The very first currency inserted is always made base (``is_base=True``).
2. **Promoting** a currency to base atomically demotes the current base and
   promotes the new one — both in a single transaction.
3. **Cannot delete** the base currency while other currencies exist.
4. **Cannot delete** a currency that is referenced by any ``messages`` row.
5. Base currency ``default_rate`` is always ``1`` and cannot be changed.
6. Dated exchange rates cannot be added for the base currency.
7. ``code`` must match ``^[A-Z]{3}$``; ``default_rate`` and ``rate`` must be > 0.

All functions receive an open :class:`~sqlalchemy.ext.asyncio.AsyncSession` and
do **not** call ``commit`` — the caller is responsible for committing or rolling
back.  This keeps batch operations atomic.
"""

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Currency, ExchangeRate, Message

# Compiled once at import time for performance
_CODE_RE = re.compile(r"^[A-Z]{3}$")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_code(code: str) -> None:
    """Raise ``ValueError`` if *code* does not match ``^[A-Z]{3}$``."""
    if not _CODE_RE.match(code):
        raise ValueError(
            f"Currency code {code!r} is invalid: must be exactly 3 uppercase ASCII letters"
        )


def _validate_rate(rate: Decimal, field_name: str = "rate") -> None:
    """Raise ``ValueError`` if *rate* is not positive."""
    if rate <= Decimal("0"):
        raise ValueError(f"{field_name} must be greater than 0, got {rate}")


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def list_currencies(session: AsyncSession) -> list[Currency]:
    """Return all currencies ordered by code."""
    result = await session.execute(select(Currency).order_by(Currency.code))
    return list(result.scalars().all())


async def get_currency_by_id(session: AsyncSession, currency_id: int) -> Currency | None:
    """Return a single currency by primary key, or ``None``."""
    result = await session.execute(
        select(Currency).where(Currency.id == currency_id)
    )
    return result.scalar_one_or_none()


async def get_currency_by_code(session: AsyncSession, code: str) -> Currency | None:
    """Return a single currency by ISO code (case-sensitive), or ``None``."""
    result = await session.execute(
        select(Currency).where(Currency.code == code)
    )
    return result.scalar_one_or_none()


async def get_base_currency(session: AsyncSession) -> Currency | None:
    """Return the currency with ``is_base=True``, or ``None`` if none exist."""
    result = await session.execute(
        select(Currency).where(Currency.is_base.is_(True))
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Write operations — currencies
# ---------------------------------------------------------------------------

async def create_currency(
    session: AsyncSession,
    code: str,
    default_rate: Decimal,
) -> Currency:
    """Create a new currency.

    Business rules applied:
    - ``code`` must match ``^[A-Z]{3}$``.
    - ``default_rate`` must be > 0.
    - If no currencies exist yet, the new one is forced to ``is_base=True``
      with ``default_rate=1`` (the invariant that every DB always has exactly
      one base currency once any currency exists).
    - Otherwise ``is_base=False``.

    Returns the flushed (but not committed) :class:`Currency` instance.
    """
    _validate_code(code)
    _validate_rate(default_rate, "default_rate")

    # First currency ever → force base
    count_result = await session.execute(select(func.count(Currency.id)))
    is_first = (count_result.scalar() or 0) == 0

    currency = Currency(
        code=code,
        is_base=is_first,
        default_rate=Decimal("1") if is_first else default_rate,
    )
    session.add(currency)
    await session.flush()
    await session.refresh(currency)
    return currency


async def update_currency(
    session: AsyncSession,
    currency_id: int,
    default_rate: Decimal,
) -> Currency | None:
    """Update the ``default_rate`` of a non-base currency.

    The base currency's ``default_rate`` is always ``1`` and is not editable
    via this function.  Attempting to update the base currency raises
    ``ValueError``.

    Returns the updated :class:`Currency` or ``None`` if not found.
    """
    _validate_rate(default_rate, "default_rate")

    currency = await get_currency_by_id(session, currency_id)
    if currency is None:
        return None

    if bool(currency.is_base):
        raise ValueError("Cannot change the default_rate of the base currency (always 1)")

    currency.default_rate = default_rate  # type: ignore[assignment]
    await session.flush()
    await session.refresh(currency)
    return currency


async def promote_to_base(session: AsyncSession, currency_id: int) -> Currency:
    """Atomically promote *currency_id* to base, demoting the current base.

    Steps (within the same transaction / flush):
    1. Recalculate every other currency's ``default_rate`` relative to the new
       base by dividing by the new base's current ``default_rate`` (``factor``).
    2. Recalculate every dated ``ExchangeRate`` for non-target currencies the
       same way.
    3. Move the target's own dated rates to the old base currency as inverted
       rates (1 / original_rate), then delete the target's dated rates.
    4. Set ``is_base=False`` on the current base (if any).
    5. Set ``is_base=True`` and ``default_rate=1`` on the target currency.

    Raises ``ValueError`` if *currency_id* does not exist.
    """
    from sqlalchemy import delete as sa_delete, update

    target = await get_currency_by_id(session, currency_id)
    if target is None:
        raise ValueError(f"Currency with id={currency_id} not found")

    if bool(target.is_base):
        # Already base — nothing to do
        return target

    factor = Decimal(str(target.default_rate))

    # Fetch the old base and target's dated rates before any modifications
    old_base = await get_base_currency(session)
    target_rates_result = await session.execute(
        select(ExchangeRate).where(ExchangeRate.currency_id == currency_id)
    )
    target_rates = list(target_rates_result.scalars().all())

    # Recalculate default_rate for every currency except the new base
    await session.execute(
        update(Currency)
        .where(Currency.id != currency_id)
        .values(default_rate=Currency.default_rate / factor)
    )

    # Recalculate dated exchange rates for non-target currencies only
    await session.execute(
        update(ExchangeRate)
        .where(ExchangeRate.currency_id != currency_id)
        .values(rate=ExchangeRate.rate / factor)
    )

    # Delete target's dated exchange rates — they will be moved to the old base
    await session.execute(
        sa_delete(ExchangeRate).where(ExchangeRate.currency_id == currency_id)
    )

    # Demote current base and promote target
    await session.execute(
        update(Currency)
        .where(Currency.is_base.is_(True))
        .values(is_base=False)
    )
    await session.execute(
        update(Currency)
        .where(Currency.id == currency_id)
        .values(is_base=True, default_rate=Decimal("1"))
    )

    # Create inverted dated rates for the old base (now a non-base currency)
    if old_base is not None:
        for tr in target_rates:
            session.add(ExchangeRate(
                currency_id=old_base.id,
                rate=Decimal("1") / Decimal(str(tr.rate)),
                rate_date=tr.rate_date,
            ))

    await session.flush()
    await session.refresh(target)
    return target


async def delete_currency(session: AsyncSession, currency_id: int) -> bool:
    """Delete a currency by id.

    Raises:
        ValueError: if the currency is the base and other currencies exist.
        ValueError: if any ``messages`` row references the currency.

    Returns ``True`` if deleted, ``False`` if not found.
    """
    from sqlalchemy import delete as sa_delete

    currency = await get_currency_by_id(session, currency_id)
    if currency is None:
        return False

    # Cannot delete base while other currencies exist
    if bool(currency.is_base):
        other_count_result = await session.execute(
            select(func.count(Currency.id)).where(Currency.id != currency_id)
        )
        other_count = other_count_result.scalar() or 0
        if other_count > 0:
            raise ValueError(
                "Нельзя удалить базовую валюту, пока существуют другие валюты"
            )

    # Cannot delete if referenced by messages
    ref_count_result = await session.execute(
        select(func.count(Message.id)).where(Message.currency_id == currency_id)
    )
    ref_count = ref_count_result.scalar() or 0
    if ref_count > 0:
        raise ValueError(
            "Нельзя удалить валюту: на неё ссылаются расходы"
        )

    await session.execute(
        sa_delete(Currency).where(Currency.id == currency_id)
    )
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Exchange rate operations
# ---------------------------------------------------------------------------

async def list_exchange_rates(
    session: AsyncSession, currency_id: int
) -> list[ExchangeRate]:
    """Return all dated rates for *currency_id* ordered by date descending."""
    result = await session.execute(
        select(ExchangeRate)
        .where(ExchangeRate.currency_id == currency_id)
        .order_by(ExchangeRate.rate_date.desc())
    )
    return list(result.scalars().all())


async def create_exchange_rate(
    session: AsyncSession,
    currency_id: int,
    rate: Decimal,
    rate_date: date,
) -> ExchangeRate:
    """Create a dated exchange rate for *currency_id*.

    Raises:
        ValueError: if *rate* <= 0.
        ValueError: if the currency is the base currency.
        ValueError: if *currency_id* does not exist.
    """
    _validate_rate(rate)

    currency = await get_currency_by_id(session, currency_id)
    if currency is None:
        raise ValueError(f"Currency with id={currency_id} not found")
    if bool(currency.is_base):
        raise ValueError("Cannot add a dated rate for the base currency")

    exchange_rate = ExchangeRate(
        currency_id=currency_id,
        rate=rate,
        rate_date=rate_date,
    )
    session.add(exchange_rate)
    await session.flush()
    await session.refresh(exchange_rate)
    return exchange_rate


async def update_exchange_rate(
    session: AsyncSession,
    rate_id: int,
    rate: Decimal,
) -> ExchangeRate | None:
    """Update the ``rate`` value of an existing dated exchange rate.

    Returns the updated :class:`ExchangeRate` or ``None`` if not found.
    Raises ``ValueError`` if *rate* <= 0.
    """
    _validate_rate(rate)

    result = await session.execute(
        select(ExchangeRate).where(ExchangeRate.id == rate_id)
    )
    exchange_rate = result.scalar_one_or_none()
    if exchange_rate is None:
        return None

    exchange_rate.rate = rate  # type: ignore[assignment]
    await session.flush()
    await session.refresh(exchange_rate)
    return exchange_rate


async def delete_exchange_rate(session: AsyncSession, rate_id: int) -> bool:
    """Delete a dated exchange rate by id.

    Returns ``True`` if deleted, ``False`` if not found.
    """
    from sqlalchemy import delete as sa_delete

    rate = await session.execute(
        select(ExchangeRate).where(ExchangeRate.id == rate_id)
    )
    if rate.scalar_one_or_none() is None:
        return False

    await session.execute(
        sa_delete(ExchangeRate).where(ExchangeRate.id == rate_id)
    )
    await session.flush()
    return True
