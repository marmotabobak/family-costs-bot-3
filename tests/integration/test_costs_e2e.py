"""End-to-end tests for costs management with real database."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bot.config import Environment
from bot.db.dependencies import get_session
from bot.db.repositories.messages import (
    delete_message_by_id,
    get_all_costs_paginated,
    get_message_by_id,
    save_message,
    update_message,
)
from bot.web.app import app
from bot.web.costs import SESSION_COOKIE, auth_sessions, login_attempts


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Clean up sessions after each test."""
    yield
    auth_sessions.clear()
    login_attempts.clear()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated test client with CSRF token."""
    token = "e2e-auth-token"
    csrf_token = "e2e-csrf-token"
    auth_sessions[token] = {
        "authenticated": True,
        "created_at": datetime.now(),
        "csrf_token": csrf_token,
    }
    client.cookies.set(SESSION_COOKIE, token)
    return client, csrf_token


class TestAuthenticationFlow:
    """E2E tests for authentication flow."""

    @patch("bot.web.costs.settings")
    def test_full_login_flow(self, mock_settings, client):
        """Test complete login -> use -> logout flow."""
        mock_settings.web_password = "e2e-test-password"
        mock_settings.env = Environment.test

        # 1. Access costs page - should redirect to login
        response = client.get("/costs", follow_redirects=False)
        assert response.status_code == 303
        assert "/costs/login" in response.headers["location"]

        # 2. Login
        response = client.post(
            "/costs/login",
            data={"password": "e2e-test-password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert SESSION_COOKIE in response.cookies

        # 3. Access costs page - should work now (with mock to avoid DB)
        with patch("bot.web.costs.get_db_session") as mock_get_session:
            from unittest.mock import AsyncMock, MagicMock

            mock_session = MagicMock()
            mock_paginated = MagicMock()
            mock_paginated.items = []
            mock_paginated.total = 0
            mock_paginated.page = 1
            mock_paginated.per_page = 20
            mock_paginated.total_pages = 1

            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("bot.web.costs.get_all_costs_paginated", return_value=mock_paginated):
                response = client.get("/costs")
                assert response.status_code == 200
                assert "Расходы" in response.text

        # 4. Logout
        response = client.get("/costs/logout", follow_redirects=False)
        assert response.status_code == 303

        # 5. Access costs page again - should redirect to login
        response = client.get("/costs", follow_redirects=False)
        assert response.status_code == 303
        assert "/costs/login" in response.headers["location"]


class TestValidationE2E:
    """E2E tests for form validation."""

    def test_amount_validation_preserves_form_data(self, authenticated_client):
        """Test that form data is preserved on validation error."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Сохраненное имя",
                "amount": "invalid",
                "user_id": "123",
                "csrf_token": csrf_token,
            },
        )

        assert response.status_code == 200
        assert "Некорректная сумма" in response.text
        assert "Сохраненное имя" in response.text  # Form data preserved

    def test_user_id_validation(self, authenticated_client):
        """Test user_id validation."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "-5",
                "csrf_token": csrf_token,
            },
        )

        assert response.status_code == 200
        assert "User ID должен быть больше 0" in response.text

    def test_date_validation(self, authenticated_client):
        """Test date validation."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "1",
                "created_at": "invalid-date",
                "csrf_token": csrf_token,
            },
        )

        assert response.status_code == 200
        assert "Некорректная дата" in response.text


class TestRepositoryFunctionsE2E:
    """E2E tests for new repository functions with real DB."""

    @pytest.mark.asyncio
    async def test_get_all_costs_paginated(self):
        """Test get_all_costs_paginated with real DB."""
        # Create test data
        async with get_session() as session:
            for i in range(5):
                await save_message(session, user_id=444, text=f"Repo test {i} 100")
            await session.commit()

        # Test pagination
        async with get_session() as session:
            result = await get_all_costs_paginated(session, page=1, per_page=3)

            assert result.total >= 5
            assert len(result.items) == 3
            assert result.page == 1
            assert result.per_page == 3

    @pytest.mark.asyncio
    async def test_get_all_costs_paginated_second_page(self):
        """Test pagination second page."""
        # Create test data
        async with get_session() as session:
            for i in range(10):
                await save_message(session, user_id=445, text=f"Page test {i} 100")
            await session.commit()

        # Test second page
        async with get_session() as session:
            result = await get_all_costs_paginated(session, page=2, per_page=3)

            assert result.page == 2
            assert len(result.items) <= 3

    @pytest.mark.asyncio
    async def test_get_message_by_id(self):
        """Test get_message_by_id with real DB."""
        # Create test data
        async with get_session() as session:
            message = await save_message(session, user_id=333, text="Get by ID 100")
            await session.commit()
            message_id = message.id

        # Test retrieval
        async with get_session() as session:
            result = await get_message_by_id(session, message_id)

            assert result is not None
            assert result.id == message_id
            assert result.text == "Get by ID 100"

    @pytest.mark.asyncio
    async def test_get_message_by_id_not_found(self):
        """Test get_message_by_id returns None for non-existent."""
        async with get_session() as session:
            result = await get_message_by_id(session, 999999999)
            assert result is None

    @pytest.mark.asyncio
    async def test_update_message(self):
        """Test update_message with real DB."""
        # Create test data
        async with get_session() as session:
            message = await save_message(session, user_id=222, text="Original 100")
            await session.commit()
            message_id = message.id

        # Test update
        async with get_session() as session:
            result = await update_message(
                session,
                message_id=message_id,
                text="Updated 200",
                user_id=223,
            )
            await session.commit()

            assert result is not None
            assert result.text == "Updated 200"
            assert result.user_id == 223

    @pytest.mark.asyncio
    async def test_update_message_not_found(self):
        """Test update_message returns None for non-existent."""
        async with get_session() as session:
            result = await update_message(
                session,
                message_id=999999999,
                text="Will not update",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_update_message_with_datetime(self):
        """Test update_message with custom datetime."""
        # Create test data
        async with get_session() as session:
            message = await save_message(session, user_id=221, text="DateTime test 100")
            await session.commit()
            message_id = message.id

        # Test update with datetime
        new_datetime = datetime(2025, 6, 15, 10, 30)
        async with get_session() as session:
            result = await update_message(
                session,
                message_id=message_id,
                text="DateTime updated 200",
                created_at=new_datetime,
            )
            await session.commit()

            assert result is not None
            # Compare date parts (ignoring timezone conversion)
            assert result.created_at.year == 2025
            assert result.created_at.month == 6
            assert result.created_at.day == 15

    @pytest.mark.asyncio
    async def test_delete_message_by_id(self):
        """Test delete_message_by_id with real DB."""
        # Create test data
        async with get_session() as session:
            message = await save_message(session, user_id=111, text="To delete 100")
            await session.commit()
            message_id = message.id

        # Test delete
        async with get_session() as session:
            result = await delete_message_by_id(session, message_id)
            await session.commit()

            assert result is True

        # Verify deleted
        async with get_session() as session:
            result = await get_message_by_id(session, message_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_delete_message_by_id_not_found(self):
        """Test delete_message_by_id returns False for non-existent."""
        async with get_session() as session:
            result = await delete_message_by_id(session, 999999999)
            assert result is False

    @pytest.mark.asyncio
    async def test_pagination_handles_invalid_page(self):
        """Test pagination handles page < 1."""
        async with get_session() as session:
            # Page 0 or negative should be treated as page 1
            result = await get_all_costs_paginated(session, page=0, per_page=10)
            assert result.page == 1

            result = await get_all_costs_paginated(session, page=-5, per_page=10)
            assert result.page == 1

    @pytest.mark.asyncio
    async def test_pagination_handles_large_page(self):
        """Test pagination handles page beyond last."""
        # Create minimal data
        async with get_session() as session:
            await save_message(session, user_id=112, text="Large page test 100")
            await session.commit()

        async with get_session() as session:
            # Request page 1000 when there's only 1 page
            result = await get_all_costs_paginated(session, page=1000, per_page=100)
            # Should be clamped to last page
            assert result.page <= result.total_pages
