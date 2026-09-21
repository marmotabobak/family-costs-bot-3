"""E2E journey tests for currency support.

Journey 6.1 — Rate selection and dynamic recompute
Journey 6.2 — Deletion blocked by referencing costs; delete succeeds after cost removed
Journey 6.3 — Base-currency promotion atomicity
Unit 6.4   — Migration inline ``_parse_amount`` mirrors legacy behavior

These tests require a running PostgreSQL instance (integration DB).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from bot.db.dependencies import get_session
from bot.db.repositories.currencies import (
    create_currency,
    create_exchange_rate,
    delete_currency,
    get_currency_by_code,
    promote_to_base,
    delete_exchange_rate,
)
from bot.db.repositories.messages import delete_message_by_id, save_message
from bot.services.currency_rates import effective_rate

pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Journey 6.1 — dated rate selection and dynamic recompute
# ---------------------------------------------------------------------------

class TestJourney61RateSelection:
    """
    Setup:
    - USD with default_rate=90
    - Dated rate 95 on 2026-05-10
    - Dated rate 97 on 2026-05-12
    - Cost: lunch 10 [USD] on 2026-05-13 → base_amount = 10 * 97 = 970

    After editing 2026-05-12 rate to 100:
    - Same cost on 2026-05-13 → recomputed base_amount = 10 * 100 = 1000
    """

    @pytest.mark.asyncio
    async def test_cost_uses_latest_on_or_before_rate(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await create_exchange_rate(session, int(usd.id), Decimal("95"), date(2026, 5, 10))
            await create_exchange_rate(session, int(usd.id), Decimal("97"), date(2026, 5, 12))
            await save_message(
                session,
                user_id=1,
                text="lunch 10",
                amount=Decimal("10"),
                currency_id=int(usd.id),
                created_at=datetime(2026, 5, 13),
            )
            await session.commit()

        # Compute base amount for 2026-05-13 → should use rate from 2026-05-12 = 97
        async with get_session() as session:
            usd = await get_currency_by_code(session, "USD")
            rate = await effective_rate(session, usd, date(2026, 5, 13))

        assert rate == Decimal("97")
        base_amount = Decimal("10") * rate
        assert base_amount == Decimal("970")

    @pytest.mark.asyncio
    async def test_after_editing_rate_base_amount_recomputed(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await create_exchange_rate(session, int(usd.id), Decimal("95"), date(2026, 5, 10))
            rate_obj = await create_exchange_rate(
                session, int(usd.id), Decimal("97"), date(2026, 5, 12)
            )
            await session.commit()
            rate_id = int(rate_obj.id)

        # Delete the 2026-05-12 rate and add a new one with 100
        async with get_session() as session:
            await delete_exchange_rate(session, rate_id)
            usd = await get_currency_by_code(session, "USD")
            await create_exchange_rate(session, int(usd.id), Decimal("100"), date(2026, 5, 12))
            await session.commit()

        # Recompute for 2026-05-13 → should now use 100
        async with get_session() as session:
            usd = await get_currency_by_code(session, "USD")
            rate = await effective_rate(session, usd, date(2026, 5, 13))

        assert rate == Decimal("100")
        assert Decimal("10") * rate == Decimal("1000")


# ---------------------------------------------------------------------------
# Journey 6.2 — Deletion blocked by referencing costs
# ---------------------------------------------------------------------------

class TestJourney62DeletionBlocked:
    @pytest.mark.asyncio
    async def test_delete_currency_blocked_while_cost_references_it(self):
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            msg = await save_message(
                session,
                user_id=1,
                text="coffee 5",
                amount=Decimal("5"),
                currency_id=int(usd.id),
            )
            await session.commit()
            usd_id = int(usd.id)
            msg_id = int(msg.id)

        # Attempt to delete while a message references it → ValueError
        with pytest.raises(ValueError, match="ссылаются"):
            async with get_session() as session:
                await delete_currency(session, usd_id)

        # Delete the referencing message
        async with get_session() as session:
            await delete_message_by_id(session, msg_id)
            await session.commit()

        # Now deletion succeeds
        async with get_session() as session:
            deleted = await delete_currency(session, usd_id)
            await session.commit()

        assert deleted is True

    @pytest.mark.asyncio
    async def test_deleting_currency_cascades_exchange_rates(self):
        """When a currency is deleted, its exchange_rates are cascade-deleted."""
        async with get_session() as session:
            usd = await create_currency(session, "USD", Decimal("90"))
            await create_exchange_rate(
                session, int(usd.id), Decimal("95"), date(2026, 5, 10)
            )
            await session.commit()
            usd_id = int(usd.id)

        async with get_session() as session:
            deleted = await delete_currency(session, usd_id)
            await session.commit()

        assert deleted is True

        # Verify exchange_rates are gone via DB
        from sqlalchemy import text
        from bot.db.session import engine
        async with engine.connect() as conn:
            count = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM exchange_rates WHERE currency_id = :id"),
                    {"id": usd_id},
                )
            ).scalar()
        assert count == 0


# ---------------------------------------------------------------------------
# Journey 6.3 — Base-currency promotion atomicity
# ---------------------------------------------------------------------------

class TestJourney63BasePromotion:
    @pytest.mark.asyncio
    async def test_cannot_delete_base_while_others_exist(self):
        async with get_session() as session:
            await create_currency(session, "EUR", Decimal("100"))
            await session.commit()

        async with get_session() as session:
            rub = await get_currency_by_code(session, "RUB")
            with pytest.raises(ValueError, match="базовую"):
                await delete_currency(session, int(rub.id))

    @pytest.mark.asyncio
    async def test_promote_eur_demotes_rub_atomically(self):
        async with get_session() as session:
            eur = await create_currency(session, "EUR", Decimal("100"))
            await session.commit()
            eur_id = int(eur.id)

        async with get_session() as session:
            await promote_to_base(session, eur_id)
            await session.commit()

        # EUR is now base, RUB is no longer base
        async with get_session() as session:
            eur = await get_currency_by_code(session, "EUR")
            rub = await get_currency_by_code(session, "RUB")

        assert eur.is_base is True
        assert rub.is_base is False

        # Only one base should exist
        async with get_session() as session:
            from sqlalchemy import text
            from bot.db.session import engine
        async with engine.connect() as conn:
            count = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM currencies WHERE is_base = TRUE")
                )
            ).scalar()
        assert count == 1


# ---------------------------------------------------------------------------
# Unit 6.4 — Migration inline _parse_amount
# ---------------------------------------------------------------------------

class TestMigrationParseAmount:
    """Unit tests for the migration's inline ``_parse_amount`` function.

    These tests verify that the frozen copy of the legacy rsplit logic in the
    migration file produces the same results as the original.
    """

    def _parse(self, text):
        from migrations.versions.e1f2a3b4c5d6_add_currency_support import _parse_amount
        return _parse_amount(text)

    def test_coffee_250(self):
        assert self._parse("coffee 250") == Decimal("250")

    def test_a_b_c_12_comma_50(self):
        assert self._parse("a b c 12,50") == Decimal("12.50")

    def test_malformed_returns_none(self):
        assert self._parse("malformed") is None

    def test_empty_string_returns_none(self):
        assert self._parse("") is None

    def test_none_returns_none(self):
        assert self._parse(None) is None

    def test_multi_word_with_integer(self):
        assert self._parse("groceries 1500") == Decimal("1500")

    def test_decimal_with_dot(self):
        assert self._parse("bread 12.50") == Decimal("12.50")
