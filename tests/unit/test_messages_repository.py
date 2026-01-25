"""Tests for messages repository."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.db.repositories.messages import (
    UserCostsStats,
    delete_messages_by_ids,
    get_unique_user_ids,
    get_user_available_months,
    get_user_costs_by_month,
    get_user_costs_stats,
    get_user_recent_costs,
    save_message,
)


@pytest.fixture
def mock_session():
    """Create mock async session."""
    session = AsyncMock()
    return session


class TestUserCostsStats:
    """Tests for UserCostsStats dataclass."""

    def test_dataclass_fields(self):
        """Stats has all required fields."""
        stats = UserCostsStats(
            total_amount=Decimal("100.50"),
            count=5,
            first_date=datetime(2026, 1, 1),
            last_date=datetime(2026, 1, 31),
        )

        assert stats.total_amount == Decimal("100.50")
        assert stats.count == 5
        assert stats.first_date == datetime(2026, 1, 1)
        assert stats.last_date == datetime(2026, 1, 31)

    def test_dataclass_with_none_dates(self):
        """Stats allows None dates for empty results."""
        stats = UserCostsStats(
            total_amount=Decimal("0"),
            count=0,
            first_date=None,
            last_date=None,
        )

        assert stats.first_date is None
        assert stats.last_date is None


class TestGetUserCostsStats:
    """Tests for get_user_costs_stats function."""

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        """Returns zero stats when no messages."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        stats = await get_user_costs_stats(mock_session, user_id=123)

        assert stats.total_amount == Decimal("0")
        assert stats.count == 0
        assert stats.first_date is None
        assert stats.last_date is None

    @pytest.mark.asyncio
    async def test_calculates_total(self, mock_session):
        """Calculates total from message texts."""
        now = datetime.now()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=now),
            MagicMock(text="Хлеб 50.50", created_at=now),
            MagicMock(text="Сыр 200,25", created_at=now),
        ]
        mock_session.execute.return_value = mock_result

        stats = await get_user_costs_stats(mock_session, user_id=123)

        assert stats.total_amount == Decimal("350.75")
        assert stats.count == 3

    @pytest.mark.asyncio
    async def test_handles_invalid_amount(self, mock_session):
        """Skips messages with invalid amount format."""
        now = datetime.now()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=now),
            MagicMock(text="Невалидная строка", created_at=now),
            MagicMock(text="Хлеб abc", created_at=now),
        ]
        mock_session.execute.return_value = mock_result

        stats = await get_user_costs_stats(mock_session, user_id=123)

        assert stats.total_amount == Decimal("100")
        assert stats.count == 3  # count includes all rows

    @pytest.mark.asyncio
    async def test_returns_first_and_last_dates(self, mock_session):
        """Returns correct first and last dates."""
        first_date = datetime(2026, 1, 1, 10, 0)
        last_date = datetime(2026, 1, 31, 20, 0)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=first_date),
            MagicMock(text="Хлеб 50", created_at=datetime(2026, 1, 15)),
            MagicMock(text="Сыр 200", created_at=last_date),
        ]
        mock_session.execute.return_value = mock_result

        stats = await get_user_costs_stats(mock_session, user_id=123)

        assert stats.first_date == first_date
        assert stats.last_date == last_date


class TestGetUserRecentCosts:
    """Tests for get_user_recent_costs function."""

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        """Returns empty list when no messages."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        costs = await get_user_recent_costs(mock_session, user_id=123)

        assert costs == []

    @pytest.mark.asyncio
    async def test_parses_costs(self, mock_session):
        """Parses cost name and amount from text."""
        now = datetime.now()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=now),
            MagicMock(text="Хлеб белый 50.50", created_at=now),
        ]
        mock_session.execute.return_value = mock_result

        costs = await get_user_recent_costs(mock_session, user_id=123)

        assert len(costs) == 2
        assert costs[0] == ("Молоко", Decimal("100"), now)
        assert costs[1] == ("Хлеб белый", Decimal("50.50"), now)

    @pytest.mark.asyncio
    async def test_skips_invalid_format(self, mock_session):
        """Skips messages that can't be parsed."""
        now = datetime.now()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=now),
            MagicMock(text="Невалидная", created_at=now),
            MagicMock(text="Хлеб abc", created_at=now),
        ]
        mock_session.execute.return_value = mock_result

        costs = await get_user_recent_costs(mock_session, user_id=123)

        assert len(costs) == 1
        assert costs[0][0] == "Молоко"

    @pytest.mark.asyncio
    async def test_handles_comma_decimal(self, mock_session):
        """Handles comma as decimal separator."""
        now = datetime.now()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100,50", created_at=now),
        ]
        mock_session.execute.return_value = mock_result

        costs = await get_user_recent_costs(mock_session, user_id=123)

        assert costs[0][1] == Decimal("100.50")


class TestGetUniqueUserIds:
    """Tests for get_unique_user_ids function."""

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        """Returns empty list when no users."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        user_ids = await get_unique_user_ids(mock_session)

        assert user_ids == []

    @pytest.mark.asyncio
    async def test_returns_user_ids(self, mock_session):
        """Returns list of unique user IDs."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [123, 456, 789]
        mock_session.execute.return_value = mock_result

        user_ids = await get_unique_user_ids(mock_session)

        assert user_ids == [123, 456, 789]


class TestGetUserCostsByMonth:
    """Tests for get_user_costs_by_month function."""

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        """Returns empty list when no costs for month."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        costs = await get_user_costs_by_month(
            mock_session, user_id=123, year=2026, month=1
        )

        assert costs == []

    @pytest.mark.asyncio
    async def test_returns_costs_for_month(self, mock_session):
        """Returns parsed costs for specified month."""
        jan_date = datetime(2026, 1, 15)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=jan_date),
            MagicMock(text="Хлеб 50", created_at=jan_date),
        ]
        mock_session.execute.return_value = mock_result

        costs = await get_user_costs_by_month(
            mock_session, user_id=123, year=2026, month=1
        )

        assert len(costs) == 2
        assert costs[0] == ("Молоко", Decimal("100"), jan_date)
        assert costs[1] == ("Хлеб", Decimal("50"), jan_date)

    @pytest.mark.asyncio
    async def test_skips_invalid_format(self, mock_session):
        """Skips messages with invalid format."""
        jan_date = datetime(2026, 1, 15)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(text="Молоко 100", created_at=jan_date),
            MagicMock(text="Невалидная строка", created_at=jan_date),
        ]
        mock_session.execute.return_value = mock_result

        costs = await get_user_costs_by_month(
            mock_session, user_id=123, year=2026, month=1
        )

        assert len(costs) == 1


class TestGetUserAvailableMonths:
    """Tests for get_user_available_months function."""

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        """Returns empty list when no data."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        months = await get_user_available_months(mock_session, user_id=123)

        assert months == []

    @pytest.mark.asyncio
    async def test_returns_year_month_tuples(self, mock_session):
        """Returns list of (year, month) tuples."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(year=2026, month=1),
            MagicMock(year=2025, month=12),
            MagicMock(year=2025, month=11),
        ]
        mock_session.execute.return_value = mock_result

        months = await get_user_available_months(mock_session, user_id=123)

        assert months == [(2026, 1), (2025, 12), (2025, 11)]

    @pytest.mark.asyncio
    async def test_converts_to_int(self, mock_session):
        """Converts year and month to int."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(year=2026.0, month=1.0),  # floats from DB
        ]
        mock_session.execute.return_value = mock_result

        months = await get_user_available_months(mock_session, user_id=123)

        assert months == [(2026, 1)]
        assert isinstance(months[0][0], int)
        assert isinstance(months[0][1], int)


class TestDeleteMessagesByIds:
    """Tests for delete_messages_by_ids function."""

    @pytest.mark.asyncio
    async def test_returns_deleted_count(self, mock_session):
        """Returns number of deleted rows."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await delete_messages_by_ids(
            mock_session, message_ids=[1, 2, 3], user_id=123
        )

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, mock_session):
        """Returns 0 when rowcount is None."""
        mock_result = MagicMock()
        mock_result.rowcount = None
        mock_session.execute.return_value = mock_result

        count = await delete_messages_by_ids(
            mock_session, message_ids=[1, 2, 3], user_id=123
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_ids_list(self, mock_session):
        """Handles empty IDs list."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await delete_messages_by_ids(
            mock_session, message_ids=[], user_id=123
        )

        assert count == 0


class TestSaveMessage:
    """Tests for save_message function."""

    @pytest.mark.asyncio
    async def test_creates_message(self, mock_session):
        """Creates message with user_id and text."""
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        message = await save_message(
            mock_session, user_id=123, text="Молоко 100"
        )

        assert message.user_id == 123
        assert message.text == "Молоко 100"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_custom_created_at(self, mock_session):
        """Sets custom created_at when provided."""
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()
        custom_date = datetime(2026, 1, 15, 10, 30)

        message = await save_message(
            mock_session,
            user_id=123,
            text="Молоко 100",
            created_at=custom_date,
        )

        assert message.created_at == custom_date

    @pytest.mark.asyncio
    async def test_no_commit_called(self, mock_session):
        """Does not call commit (caller responsibility)."""
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.commit = AsyncMock()

        await save_message(mock_session, user_id=123, text="Молоко 100")

        mock_session.commit.assert_not_called()
