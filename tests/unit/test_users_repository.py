"""Unit tests for users repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.db.repositories.users import (
    count_admins,
    create_user,
    delete_user,
    get_all_telegram_ids,
    get_all_users,
    get_user_by_id,
    get_user_by_telegram_id,
    update_user,
    update_user_password,
)


@pytest.fixture
def mock_session():
    """Мок асинхронной сессии БД."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_user(id=1, telegram_id=123, name="Иван", role="user", password_hash=None):
    """Helper to create a mock User object."""
    user = MagicMock()
    user.id = id
    user.telegram_id = telegram_id
    user.name = name
    user.role = role
    user.password_hash = password_hash
    return user


class TestGetAllUsers:
    """Tests for get_all_users."""

    @pytest.mark.asyncio
    async def test_returns_list_of_users(self, mock_session):
        """Returns list from query result."""
        users = [_make_user(1, 111, "Алёна"), _make_user(2, 222, "Иван")]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = users
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_all_users(mock_session)

        assert result == users
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_users(self, mock_session):
        """Returns empty list when table is empty."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_all_users(mock_session)

        assert result == []


class TestGetUserById:
    """Tests for get_user_by_id."""

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self, mock_session):
        """Returns user for valid ID."""
        user = _make_user(1, 123, "Иван")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_user_by_id(mock_session, 1)

        assert result == user

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        """Returns None for invalid ID."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_user_by_id(mock_session, 999)

        assert result is None


class TestGetUserByTelegramId:
    """Tests for get_user_by_telegram_id."""

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self, mock_session):
        """Returns user for valid telegram_id."""
        user = _make_user(1, 12345, "Иван")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_user_by_telegram_id(mock_session, 12345)

        assert result == user

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        """Returns None for unknown telegram_id."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_user_by_telegram_id(mock_session, 99999)

        assert result is None


class TestCreateUser:
    """Tests for create_user."""

    @pytest.mark.asyncio
    async def test_creates_and_returns_user(self, mock_session):
        """Creates user, flushes, refreshes, returns it."""
        await create_user(mock_session, telegram_id=123, name="Иван")

        mock_session.add.assert_called_once()
        added_user = mock_session.add.call_args[0][0]
        assert added_user.telegram_id == 123
        assert added_user.name == "Иван"
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(added_user)

    @pytest.mark.asyncio
    async def test_creates_user_with_password_hash(self, mock_session):
        """Creates user with password hash."""
        await create_user(mock_session, telegram_id=123, name="Иван", password_hash="hashed_password")

        mock_session.add.assert_called_once()
        added_user = mock_session.add.call_args[0][0]
        assert added_user.telegram_id == 123
        assert added_user.name == "Иван"
        assert added_user.password_hash == "hashed_password"
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(added_user)


class TestUpdateUser:
    """Tests for update_user."""

    @pytest.mark.asyncio
    async def test_updates_and_returns_user(self, mock_session):
        """Updates existing user fields."""
        existing = _make_user(1, 123, "Старое имя")
        # get_user_by_id calls session.execute internally
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await update_user(mock_session, user_id=1, telegram_id=456, name="Новое имя")

        assert result == existing
        assert existing.telegram_id == 456
        assert existing.name == "Новое имя"
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        """Returns None when user doesn't exist."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await update_user(mock_session, user_id=999, telegram_id=456, name="Имя")

        assert result is None


class TestDeleteUser:
    """Tests for delete_user."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_session):
        """Returns True when user is found and deleted."""
        result_mock = MagicMock()
        result_mock.rowcount = 1
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await delete_user(mock_session, user_id=1)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_session):
        """Returns False when no rows affected."""
        result_mock = MagicMock()
        result_mock.rowcount = 0
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await delete_user(mock_session, user_id=999)

        assert result is False


class TestGetAllTelegramIds:
    """Tests for get_all_telegram_ids."""

    @pytest.mark.asyncio
    async def test_returns_list_of_ids(self, mock_session):
        """Returns ordered list of telegram IDs."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [111, 222, 333]
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_all_telegram_ids(mock_session)

        assert result == [111, 222, 333]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_users(self, mock_session):
        """Returns empty list when no users exist."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await get_all_telegram_ids(mock_session)

        assert result == []


class TestUpdateUserPassword:
    """Tests for update_user_password."""

    @pytest.mark.asyncio
    async def test_updates_password_hash(self, mock_session):
        """Updates user password hash successfully."""
        existing = _make_user(1, 123, "Иван", password_hash="old_hash")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await update_user_password(mock_session, user_id=1, password_hash="new_hash")

        assert result == existing
        assert existing.password_hash == "new_hash"
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_user_not_found(self, mock_session):
        """Returns None when user doesn't exist."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await update_user_password(mock_session, user_id=999, password_hash="new_hash")

        assert result is None


class TestCountAdmins:
    """Tests for count_admins."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_admins(self, mock_session):
        """Returns 0 when there are no admins."""
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 0
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await count_admins(mock_session)

        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_count_of_admins(self, mock_session):
        """Returns count of admin users."""
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 3
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await count_admins(mock_session)

        assert result == 3
