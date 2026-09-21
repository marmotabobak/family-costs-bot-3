"""Integration tests for ``bot.db.repositories.currencies``.

Tests require a running PostgreSQL instance with the currency-support
migration already applied (``make migrate``).

The ``cleanup_db`` autouse fixture (in conftest.py) cleans messages and
exchange_rates before each test and ensures RUB is present as the base
currency, so individual tests start with a single known state.
"""

from datetime import date
from decimal import Decimal

import pytest

from bot.db.dependencies import get_session
from bot.db.repositories.currencies import (
    create_currency,
    create_exchange_rate,
    delete_currency,
    delete_exchange_rate,
    get_base_currency,
    get_currency_by_code,
    get_currency_by_id,
    list_currencies,
    list_exchange_rates,
    promote_to_base,
    update_currency,
)
from bot.db.repositories.messages import save_message

pytestmark = pytest.mark.serial


class TestListAndGet:
    @pytest.mark.asyncio
    async def test_list_currencies_includes_rub(self):
        async with get_session() as session:
            currencies = await list_currencies(session)
        codes = [c.code for c in currencies]
        assert "RUB" in codes

    @pytest.mark.asyncio
    async def test_get_base_currency_returns_rub(self):
        async with get_session() as session:
            base = await get_base_currency(session)
        assert base is not None
        assert base.code == "RUB"
        assert base.is_base is True

    @pytest.mark.asyncio
    async def test_get_currency_by_code_found(self):
        async with get_session() as session:
            c = await get_currency_by_code(session, "RUB")
        assert c is not None
        assert c.code == "RUB"

    @pytest.mark.asyncio
    async def test_get_currency_by_code_not_found(self):
        async with get_session() as session:
            c = await get_currency_by_code(session, "ZZZ")
        assert c is None

    @pytest.mark.asyncio
    async def test_get_currency_by_id_found(self):
        async with get_session() as session:
            base = await get_base_currency(session)
            c = await get_currency_by_id(session, int(base.id))
        assert c is not None

    @pytest.mark.asyncio
    async def test_get_currency_by_id_not_found(self):
        async with get_session() as session:
            c = await get_currency_by_id(session, 999999)
        assert c is None


class TestCreateCurrency:
    @pytest.mark.asyncio
    async def test_create_non_base_currency(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await session.commit()
        assert usd.code == "USD"
        assert usd.is_base is False
        assert Decimal(str(usd.default_rate)) == Decimal("90")

    @pytest.mark.asyncio
    async def test_create_currency_invalid_code_lowercase(self):
        with pytest.raises(ValueError, match="invalid"):
            async with get_session() as session:
                await create_currency(session, "usd", Decimal("90"))

    @pytest.mark.asyncio
    async def test_create_currency_invalid_code_length(self):
        with pytest.raises(ValueError):
            async with get_session() as session:
                await create_currency(session, "USDD", Decimal("90"))

    @pytest.mark.asyncio
    async def test_create_currency_invalid_rate_zero(self):
        with pytest.raises(ValueError, match="default_rate"):
            async with get_session() as session:
                await create_currency(session, "EUR", Decimal("0"))

    @pytest.mark.asyncio
    async def test_create_currency_invalid_rate_negative(self):
        with pytest.raises(ValueError):
            async with get_session() as session:
                await create_currency(session, "EUR", Decimal("-1"))

    @pytest.mark.asyncio
    async def test_create_first_currency_forced_base(self):
        """Delete all currencies including RUB, then create EUR; should become base."""
        from sqlalchemy import text
        async with get_session() as session:
            await session.execute(text("DELETE FROM exchange_rates"))
            await session.execute(text("DELETE FROM currencies"))
            await session.commit()

        async with get_session() as session:
            eur = await create_currency(session, "EUR", Decimal("100"))
            await session.commit()

        assert eur.is_base is True
        assert Decimal(str(eur.default_rate)) == Decimal("1")


class TestUpdateCurrency:
    @pytest.mark.asyncio
    async def test_update_default_rate(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("80"))
            await session.commit()

        async with get_session() as session:
            updated = await update_currency(session, int(usd.id), Decimal("95"))
            await session.commit()

        assert Decimal(str(updated.default_rate)) == Decimal("95")

    @pytest.mark.asyncio
    async def test_update_base_currency_raises(self):
        async with get_session() as session:
            base = await get_base_currency(session)
            with pytest.raises(ValueError, match="base"):
                await update_currency(session, int(base.id), Decimal("2"))

    @pytest.mark.asyncio
    async def test_update_not_found_returns_none(self):
        async with get_session() as session:
            result = await update_currency(session, 999999, Decimal("90"))
        assert result is None


class TestPromoteToBase:
    @pytest.mark.asyncio
    async def test_promote_demotes_old_base(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await session.commit()

        async with get_session() as session:
            promoted = await promote_to_base(session, int(usd.id))
            await session.commit()

        assert promoted.is_base is True

        async with get_session() as session:
            rub = await get_currency_by_code(session, "RUB")
        assert rub is not None
        assert rub.is_base is False

    @pytest.mark.asyncio
    async def test_promote_not_found_raises(self):
        with pytest.raises(ValueError):
            async with get_session() as session:
                await promote_to_base(session, 999999)

    @pytest.mark.asyncio
    async def test_promote_already_base_is_no_op(self):
        async with get_session() as session:
            base = await get_base_currency(session)
            result = await promote_to_base(session, int(base.id))
        assert result.is_base is True

    @pytest.mark.asyncio
    async def test_promote_recalculates_default_rates(self):
        """Changing base from RUB to EUR must scale all other default_rates."""
        # RUB (base, rate=1), EUR (rate=100), USD (rate=90)
        async with get_session() as session:
            eur = await create_currency(session, "EUR", Decimal("100"))
            usd = await create_currency(session, "USD", Decimal("90"))
            await session.commit()
            eur_id, usd_id = int(eur.id), int(usd.id)

        async with get_session() as session:
            await promote_to_base(session, eur_id)
            await session.commit()

        async with get_session() as session:
            rub = await get_currency_by_code(session, "RUB")
            usd = await get_currency_by_id(session, usd_id)
            eur = await get_currency_by_id(session, eur_id)

        assert eur.is_base is True
        assert Decimal(str(eur.default_rate)) == Decimal("1")
        # RUB: 1/100 = 0.01
        assert Decimal(str(rub.default_rate)) == Decimal("1") / Decimal("100")
        # USD: 90/100 = 0.9
        assert Decimal(str(usd.default_rate)) == Decimal("90") / Decimal("100")

    @pytest.mark.asyncio
    async def test_promote_recalculates_dated_exchange_rates(self):
        """Dated exchange rates are recalculated relative to the new base."""
        async with get_session() as session:
            eur = await create_currency(session, "EUR", Decimal("100"))
            usd = await create_currency(session, "USD", Decimal("90"))
            usd_rate = await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()
            eur_id = int(eur.id)
            usd_rate_id = int(usd_rate.id)

        async with get_session() as session:
            await promote_to_base(session, eur_id)
            await session.commit()

        async with get_session() as session:
            from sqlalchemy import select
            from bot.db.models import ExchangeRate
            result = await session.execute(
                select(ExchangeRate).where(ExchangeRate.id == usd_rate_id)
            )
            updated_rate = result.scalar_one()

        # 95 RUB per USD → 95/100 = 0.95 EUR per USD
        assert Decimal(str(updated_rate.rate)) == Decimal("95") / Decimal("100")


class TestDeleteCurrency:
    @pytest.mark.asyncio
    async def test_delete_non_base_currency(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await session.commit()

        async with get_session() as session:
            deleted = await delete_currency(session, int(usd.id))
            await session.commit()

        assert deleted is True

        async with get_session() as session:
            result = await get_currency_by_code(session, "USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_base_while_others_exist_raises(self):
        async with get_session() as session:
            await create_currency(session, "USD", Decimal("90"))
            await session.commit()

        async with get_session() as session:
            base = await get_base_currency(session)
            with pytest.raises(ValueError, match="базовую"):
                await delete_currency(session, int(base.id))

    @pytest.mark.asyncio
    async def test_delete_currency_referenced_by_message_raises(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await save_message(
                session,
                user_id=1,
                text="lunch 10",
                amount=Decimal("10"),
                currency_id=int(usd.id),
            )
            await session.commit()

        async with get_session() as session:
            with pytest.raises(ValueError, match="ссылаются"):
                await delete_currency(session, int(usd.id))

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_false(self):
        async with get_session() as session:
            result = await delete_currency(session, 999999)
        assert result is False


class TestExchangeRates:
    @pytest.mark.asyncio
    async def test_create_exchange_rate(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            rate = await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()

        assert Decimal(str(rate.rate)) == Decimal("95")
        assert rate.rate_date == date(2026, 5, 10)

    @pytest.mark.asyncio
    async def test_create_rate_for_base_currency_raises(self):
        async with get_session() as session:
            base = await get_base_currency(session)
            with pytest.raises(ValueError, match="base"):
                await create_exchange_rate(
                    session, int(base.id), Decimal("1"), date(2026, 5, 10)
                )

    @pytest.mark.asyncio
    async def test_create_rate_invalid_rate_zero_raises(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            with pytest.raises(ValueError):
                await create_exchange_rate(
                    session, int(usd.id), Decimal("0"), date(2026, 5, 10)
                )

    @pytest.mark.asyncio
    async def test_create_rate_duplicate_date_raises_integrity_error(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()

        with pytest.raises(Exception):  # IntegrityError from unique constraint
            async with get_session() as session:
                usd2 = await get_currency_by_code(session, "USD")
                await create_exchange_rate(
                    session, int(usd2.id), Decimal("97"), date(2026, 5, 10)
                )
                await session.commit()

    @pytest.mark.asyncio
    async def test_list_exchange_rates_returns_sorted_desc(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await create_exchange_rate(
                session, int(usd.id), Decimal("90"), date(2026, 5, 1)
            )
            await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()

        async with get_session() as session:
            usd = await get_currency_by_code(session, "USD")
            rates = await list_exchange_rates(session, int(usd.id))

        assert rates[0].rate_date == date(2026, 5, 10)  # most recent first
        assert rates[1].rate_date == date(2026, 5, 1)

    @pytest.mark.asyncio
    async def test_delete_exchange_rate(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            rate = await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()
            rate_id = int(rate.id)

        async with get_session() as session:
            deleted = await delete_exchange_rate(session, rate_id)
            await session.commit()

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_exchange_rate_not_found(self):
        async with get_session() as session:
            result = await delete_exchange_rate(session, 999999)
        assert result is False
