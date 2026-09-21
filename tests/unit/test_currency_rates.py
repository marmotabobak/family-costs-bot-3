"""Unit tests for ``bot.services.currency_rates``.

All tests use mocked SQLAlchemy sessions — no live DB required.

Scenarios covered:
- ``effective_rate`` for base currency → always ``Decimal("1")``.
- ``effective_rate`` with an exact-date match.
- ``effective_rate`` with only ``default_rate`` (no dated rates).
- ``effective_rate`` when dated rate exists and target_date is after it.
- Multiple dated rates → latest on-or-before is chosen.
- Target date is before all dated rates → ``default_rate`` used.
- ``RateCache.get_rate`` calls ``effective_rate`` once per (currency, date).
- ``RateCache.compute_base_amount`` multiplies by the effective rate.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.currency_rates import RateCache, effective_rate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_currency(
    id_: int,
    code: str,
    is_base: bool,
    default_rate: str,
) -> MagicMock:
    """Return a mock Currency with the given attributes."""
    c = MagicMock()
    c.id = id_
    c.code = code
    c.is_base = is_base
    c.default_rate = Decimal(default_rate)
    return c


def _make_session_returning(scalar_value) -> AsyncMock:
    """Return a mock session whose ``execute`` resolves to the given scalar."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_value
    session.execute.return_value = execute_result
    return session


# ---------------------------------------------------------------------------
# effective_rate tests
# ---------------------------------------------------------------------------

class TestEffectiveRateBaseCurrency:
    """Base currency always returns Decimal('1'), no DB query."""

    @pytest.mark.asyncio
    async def test_base_currency_returns_one(self):
        base = _make_currency(1, "RUB", True, "1")
        session = AsyncMock()

        rate = await effective_rate(session, base, date(2026, 5, 1))

        assert rate == Decimal("1")
        session.execute.assert_not_called()


class TestEffectiveRateExactDateMatch:
    """When a dated rate exists exactly on target_date it is returned."""

    @pytest.mark.asyncio
    async def test_exact_date_match_returns_dated_rate(self):
        usd = _make_currency(2, "USD", False, "90")
        session = _make_session_returning(Decimal("95"))

        rate = await effective_rate(session, usd, date(2026, 5, 10))

        assert rate == Decimal("95")


class TestEffectiveRateOnlyDefault:
    """No dated rates → default_rate is used."""

    @pytest.mark.asyncio
    async def test_no_dated_rates_uses_default(self):
        usd = _make_currency(2, "USD", False, "90")
        session = _make_session_returning(None)  # no dated rates

        rate = await effective_rate(session, usd, date(2026, 1, 1))

        assert rate == Decimal("90")


class TestEffectiveRateDatedPlusDefault:
    """When a dated rate exists for an earlier date it is used over default."""

    @pytest.mark.asyncio
    async def test_dated_rate_used_over_default(self):
        usd = _make_currency(2, "USD", False, "80")
        session = _make_session_returning(Decimal("97"))

        # target_date is after the dated rate_date → dated rate applies
        rate = await effective_rate(session, usd, date(2026, 5, 13))

        assert rate == Decimal("97")


class TestEffectiveRateDateBeforeAllDated:
    """When target_date is before all dated rates, default_rate is used."""

    @pytest.mark.asyncio
    async def test_date_before_all_dated_rates_uses_default(self):
        usd = _make_currency(2, "USD", False, "85")
        session = _make_session_returning(None)  # query returns nothing

        rate = await effective_rate(session, usd, date(2020, 1, 1))

        assert rate == Decimal("85")


class TestEffectiveRateMultipleDatedRates:
    """The query orders by rate_date DESC LIMIT 1, so we get the latest on-or-before."""

    @pytest.mark.asyncio
    async def test_multiple_dated_rates_latest_returned(self):
        usd = _make_currency(2, "USD", False, "80")
        # The DB query returns the latest — we simulate it returning 97 (2026-05-12)
        session = _make_session_returning(Decimal("97"))

        rate = await effective_rate(session, usd, date(2026, 5, 15))

        assert rate == Decimal("97")


# ---------------------------------------------------------------------------
# RateCache tests
# ---------------------------------------------------------------------------

class TestRateCache:
    """RateCache deduplicates calls to effective_rate."""

    @pytest.mark.asyncio
    async def test_get_rate_calls_effective_rate_once_per_key(self):
        """Same (currency, date) pair → effective_rate called only once."""
        usd = _make_currency(2, "USD", False, "90")
        session = AsyncMock()

        with patch(
            "bot.services.currency_rates.effective_rate",
            new_callable=AsyncMock,
            return_value=Decimal("95"),
        ) as mock_effective:
            cache = RateCache(session)
            r1 = await cache.get_rate(usd, date(2026, 5, 10))
            r2 = await cache.get_rate(usd, date(2026, 5, 10))
            r3 = await cache.get_rate(usd, date(2026, 5, 10))

        assert r1 == r2 == r3 == Decimal("95")
        mock_effective.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rate_separate_dates_call_effective_rate_separately(self):
        """Different dates for the same currency → two separate lookups."""
        usd = _make_currency(2, "USD", False, "90")
        session = AsyncMock()

        with patch(
            "bot.services.currency_rates.effective_rate",
            new_callable=AsyncMock,
            side_effect=[Decimal("95"), Decimal("97")],
        ) as mock_effective:
            cache = RateCache(session)
            r1 = await cache.get_rate(usd, date(2026, 5, 10))
            r2 = await cache.get_rate(usd, date(2026, 5, 12))

        assert r1 == Decimal("95")
        assert r2 == Decimal("97")
        assert mock_effective.call_count == 2

    @pytest.mark.asyncio
    async def test_compute_base_amount_multiplies_by_rate(self):
        """compute_base_amount = amount * effective_rate."""
        usd = _make_currency(2, "USD", False, "90")
        session = AsyncMock()

        with patch(
            "bot.services.currency_rates.effective_rate",
            new_callable=AsyncMock,
            return_value=Decimal("97"),
        ):
            cache = RateCache(session)
            base = await cache.compute_base_amount(
                Decimal("10"), usd, date(2026, 5, 13)
            )

        assert base == Decimal("970")

    @pytest.mark.asyncio
    async def test_compute_base_amount_base_currency_no_db(self):
        """For base currency, compute_base_amount = amount (rate = 1)."""
        rub = _make_currency(1, "RUB", True, "1")
        session = AsyncMock()

        cache = RateCache(session)
        base = await cache.compute_base_amount(
            Decimal("500"), rub, date(2026, 5, 1)
        )

        assert base == Decimal("500")
        session.execute.assert_not_called()
