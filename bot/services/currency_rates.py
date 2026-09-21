"""Currency rate-selection service.

Provides two public APIs:

1. :func:`effective_rate` — returns the applicable exchange rate for a
   *currency* on a given *target_date*:

   - Base currency → always ``Decimal("1")``.
   - Otherwise: the greatest dated :class:`~bot.db.models.ExchangeRate`
     with ``rate_date <= target_date``; falls back to
     ``currency.default_rate`` when no such row exists.

2. :class:`RateCache` — a lightweight per-request cache that avoids
   redundant ``effective_rate`` DB calls when the same
   ``(currency_id, date)`` pair is needed multiple times (e.g. while
   computing base amounts for a list of costs).

Usage example::

    cache = RateCache(session)
    base_amount = await cache.compute_base_amount(amount, currency, some_date)
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Currency, ExchangeRate


async def effective_rate(
    session: AsyncSession,
    currency: Currency,
    target_date: date,
) -> Decimal:
    """Return the effective exchange rate for *currency* on *target_date*.

    For the base currency this is always ``Decimal("1")`` — no DB query is
    issued.

    For non-base currencies the function looks up the most recent
    :class:`~bot.db.models.ExchangeRate` with ``rate_date <= target_date``
    (i.e. the "greatest on-or-before" semantics used in finance).  If no
    such row exists the ``currency.default_rate`` is returned.

    Args:
        session: an open async SQLAlchemy session.
        currency: the :class:`~bot.db.models.Currency` to look up.
        target_date: the date for which the rate is needed.

    Returns:
        The applicable rate as a :class:`~decimal.Decimal`.
    """
    if bool(currency.is_base):
        return Decimal("1")

    result = await session.execute(
        select(ExchangeRate.rate)
        .where(ExchangeRate.currency_id == currency.id)
        .where(ExchangeRate.rate_date <= target_date)
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return Decimal(str(row))

    return Decimal(str(currency.default_rate))


class RateCache:
    """Per-request cache for ``(currency_id, date) → Decimal`` rate lookups.

    Instantiate once per request / render and reuse across all cost lines to
    avoid redundant DB round-trips.

    Example::

        cache = RateCache(session)
        rate = await cache.get_rate(currency, some_date)
        base_amount = await cache.compute_base_amount(amount, currency, some_date)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cache: dict[tuple[int, date], Decimal] = {}

    async def get_rate(self, currency: Currency, target_date: date) -> Decimal:
        """Return the cached rate; compute and store if not yet cached.

        ``effective_rate`` is called **at most once** per unique
        ``(currency_id, target_date)`` combination across the lifetime of this
        cache instance.
        """
        key = (int(currency.id), target_date)
        if key not in self._cache:
            self._cache[key] = await effective_rate(
                self._session, currency, target_date
            )
        return self._cache[key]

    async def compute_base_amount(
        self,
        amount: Decimal,
        currency: Currency,
        target_date: date,
    ) -> Decimal:
        """Return *amount* converted to the base currency on *target_date*.

        The result is ``amount * effective_rate(currency, target_date)``.
        For the base currency this is just *amount* (rate = 1).
        """
        rate = await self.get_rate(currency, target_date)
        return amount * rate
