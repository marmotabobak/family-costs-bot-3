"""Integration tests for costs management API endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bot.config import Environment
from bot.web.app import app
from bot.web.auth import SESSION_COOKIE, auth_sessions, login_attempts


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
    """Create authenticated test client (admin role for full access)."""
    token = "test-auth-token"
    csrf_token = "test-csrf-token"
    auth_sessions[token] = {
        "authenticated": True,
        "created_at": datetime.now(),
        "csrf_token": csrf_token,
        "role": "admin",
        "telegram_id": 100,
        "user_name": "Тест Админ",
    }

    # Set cookie on client
    client.cookies.set(SESSION_COOKIE, token)
    return client, csrf_token


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


@pytest.fixture
def mock_users_form():
    """Mock _get_users_for_form to avoid real DB call on add forms."""
    with patch("bot.web.costs._get_users_for_form", new=AsyncMock(return_value=[])):
        yield


@pytest.fixture
def mock_get_all_users():
    """Mock get_all_users to avoid real DB call on edit forms."""
    with patch("bot.web.costs.get_all_users", new=AsyncMock(return_value=[])):
        yield


def _make_user(telegram_id=100, name="Тест", role="user"):
    user = MagicMock()
    user.telegram_id = telegram_id
    user.name = name
    user.role = role
    return user


@asynccontextmanager
async def _mock_db_session_ctx():
    yield AsyncMock()


class TestLoginPage:
    """Tests for GET /login endpoint."""

    def test_returns_200(self, client):
        """Login page returns 200."""
        users = [_make_user(100, "Иван")]
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            response = client.get("/login")

        assert response.status_code == 200

    def test_contains_password_form(self, client):
        """Login page contains password form."""
        users = [_make_user(100, "Иван")]
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            response = client.get("/login")

        assert 'type="password"' in response.text
        assert "Пароль" in response.text

    def test_redirects_if_authenticated(self, authenticated_client):
        """Redirects to costs list if already authenticated."""
        client, _ = authenticated_client

        response = client.get("/login", follow_redirects=False)

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]


class TestLoginEndpoint:
    """Tests for POST /login endpoint."""

    @patch("bot.web.auth.settings")
    def test_login_success(self, mock_settings, client):
        """Successful login sets session cookie."""
        mock_settings.web_password = "correct-password"
        mock_settings.env = Environment.test
        mock_settings.web_root_path = ""
        mock_settings.admin_telegram_id = None

        user = _make_user(100, "Иван", "user")
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=[user])),
            patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(return_value=user)),
        ):
            response = client.post(
                "/login",
                data={"password": "correct-password", "user_id": "100"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]
        assert SESSION_COOKIE in response.cookies

    @patch("bot.web.auth.settings")
    def test_login_wrong_password(self, mock_settings, client):
        """Wrong password shows error."""
        mock_settings.web_password = "correct-password"
        mock_settings.web_root_path = ""
        mock_settings.env = "test"

        users = [_make_user(100, "Иван")]
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            response = client.post(
                "/login",
                data={"password": "wrong-password", "user_id": "100"},
            )

        assert response.status_code == 200
        assert "Неверный пароль" in response.text

    @patch("bot.web.auth.settings")
    def test_login_no_password_configured(self, mock_settings, client):
        """Shows error when WEB_PASSWORD not set."""
        mock_settings.web_password = ""
        mock_settings.web_root_path = ""
        mock_settings.env = "test"

        users = [_make_user(100, "Иван")]
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            response = client.post(
                "/login",
                data={"password": "any-password", "user_id": "100"},
            )

        assert response.status_code == 200
        assert "WEB_PASSWORD" in response.text

    @patch("bot.web.auth.settings")
    def test_rate_limiting(self, mock_settings, client):
        """Rate limits login attempts."""
        mock_settings.web_password = "correct-password"
        mock_settings.web_root_path = ""
        mock_settings.env = "test"

        users = [_make_user(100, "Иван")]
        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session_ctx),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            # Make 5 failed attempts
            for _ in range(5):
                client.post("/login", data={"password": "wrong", "user_id": "100"})

            # 6th attempt should be rate limited
            response = client.post("/login", data={"password": "wrong", "user_id": "100"})

        assert "5 минут" in response.text


class TestLogout:
    """Tests for GET /logout endpoint."""

    def test_logout_clears_session(self, authenticated_client):
        """Logout clears session and redirects."""
        client, _ = authenticated_client

        response = client.get("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestCostsList:
    """Tests for GET /costs endpoint."""

    def test_redirects_if_unauthenticated(self, client):
        """Redirects to login if not authenticated."""
        response = client.get("/costs", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_returns_200_if_authenticated(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Returns 200 for authenticated user."""
        client, _ = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            # Mock empty costs list
            mock_paginated = MagicMock()
            mock_paginated.items = []
            mock_paginated.total = 0
            mock_paginated.page = 1
            mock_paginated.per_page = 20
            mock_paginated.total_pages = 1

            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "bot.web.costs.get_all_costs_paginated",
                return_value=mock_paginated,
            ):
                response = client.get("/costs")

        assert response.status_code == 200
        assert "Расходы" in response.text

    def test_shows_empty_message(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Shows empty state message when no costs."""
        client, _ = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_paginated = MagicMock()
            mock_paginated.items = []
            mock_paginated.total = 0
            mock_paginated.page = 1
            mock_paginated.per_page = 20
            mock_paginated.total_pages = 1

            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "bot.web.costs.get_all_costs_paginated",
                return_value=mock_paginated,
            ):
                response = client.get("/costs")

        assert "Расходов пока нет" in response.text


class TestAddCostForm:
    """Tests for GET /costs/add endpoint."""

    def test_redirects_if_unauthenticated(self, client):
        """Redirects to login if not authenticated."""
        response = client.get("/costs/add", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_returns_200_if_authenticated(self, authenticated_client, mock_users_form):
        """Returns 200 for authenticated user."""
        client, _ = authenticated_client

        response = client.get("/costs/add")

        assert response.status_code == 200
        assert "Добавить расход" in response.text

    def test_contains_csrf_token(self, authenticated_client, mock_users_form):
        """Form contains CSRF token."""
        client, csrf_token = authenticated_client

        response = client.get("/costs/add")

        assert 'name="csrf_token"' in response.text
        assert csrf_token in response.text


class TestAddCost:
    """Tests for POST /costs/add endpoint."""

    def test_redirects_if_unauthenticated(self, client):
        """Redirects to login if not authenticated."""
        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "1",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_requires_valid_csrf(self, authenticated_client):
        """Rejects invalid CSRF token."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "1",
                "csrf_token": "invalid-csrf",
            },
        )

        assert response.status_code == 403

    def test_validates_amount(self, authenticated_client, mock_users_form):
        """Validates amount format."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "not-a-number",
                "user_id": "1",
                "csrf_token": csrf_token,
            },
        )

        assert response.status_code == 200
        assert "Некорректная сумма" in response.text

    def test_validates_user_id(self, authenticated_client, mock_users_form):
        """Validates user_id > 0."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/costs/add",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "0",
                "csrf_token": csrf_token,
            },
        )

        assert response.status_code == 200
        assert "User ID должен быть больше 0" in response.text

    def test_successful_add(self, authenticated_client, mock_db_session, mock_users_form):
        """Successfully adds cost."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_message = MagicMock()
            mock_message.id = 1

            with patch(
                "bot.web.costs.save_message",
                return_value=mock_message,
            ):
                response = client.post(
                    "/costs/add",
                    data={
                        "name": "Молоко",
                        "amount": "100.50",
                        "user_id": "123",
                        "csrf_token": csrf_token,
                    },
                    follow_redirects=False,
                )

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]


class TestEditCostForm:
    """Tests for GET /costs/{id}/edit endpoint."""

    def test_redirects_if_unauthenticated(self, client):
        """Redirects to login if not authenticated."""
        response = client.get("/costs/1/edit", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_returns_404_for_missing(self, authenticated_client, mock_db_session):
        """Returns 404 for non-existent cost."""
        client, _ = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("bot.web.costs.get_message_by_id", return_value=None):
                response = client.get("/costs/999/edit")

        assert response.status_code == 404

    def test_returns_200_for_existing(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Returns 200 for existing cost."""
        client, _ = authenticated_client

        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.text = "Молоко 100"
        mock_message.user_id = 100  # Match authenticated_client telegram_id
        mock_message.created_at = datetime.now()

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("bot.web.costs.get_message_by_id", return_value=mock_message):
                response = client.get("/costs/1/edit")

        assert response.status_code == 200
        assert "Молоко" in response.text


class TestEditCost:
    """Tests for POST /costs/{id}/edit endpoint."""

    def test_requires_valid_csrf(self, authenticated_client):
        """Rejects invalid CSRF token."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/1/edit",
            data={
                "name": "Test",
                "amount": "100",
                "user_id": "1",
                "csrf_token": "invalid",
            },
        )

        assert response.status_code == 403

    def test_successful_edit(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Successfully edits cost."""
        client, csrf_token = authenticated_client

        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.text = "Хлеб 50"
        mock_message.user_id = 100
        mock_message.created_at = datetime.now()

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("bot.web.costs.get_message_by_id", return_value=mock_message):
                with patch("bot.web.costs.update_message", return_value=mock_message):
                    response = client.post(
                        "/costs/1/edit",
                        data={
                            "name": "Хлеб",
                            "amount": "50",
                            "user_id": "100",
                            "csrf_token": csrf_token,
                        },
                        follow_redirects=False,
                    )

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]


class TestDeleteCost:
    """Tests for POST /costs/{id}/delete endpoint."""

    def test_requires_valid_csrf(self, authenticated_client):
        """Rejects invalid CSRF token."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/1/delete",
            data={"csrf_token": "invalid"},
        )

        assert response.status_code == 403

    def test_successful_delete(self, authenticated_client, mock_db_session):
        """Successfully deletes cost."""
        client, csrf_token = authenticated_client

        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.user_id = 100

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("bot.web.costs.get_message_by_id", return_value=mock_message),
                patch("bot.web.costs.delete_message_by_id", return_value=True),
            ):
                response = client.post(
                    "/costs/1/delete",
                    data={"csrf_token": csrf_token},
                    follow_redirects=False,
                )

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]

    def test_returns_404_for_missing(self, authenticated_client, mock_db_session):
        """Returns 404 for non-existent cost."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("bot.web.costs.get_message_by_id", return_value=None):
                response = client.post(
                    "/costs/1/delete",
                    data={"csrf_token": csrf_token},
                )

        assert response.status_code == 404


class TestCsrfProtection:
    """Tests for CSRF protection across endpoints."""

    def test_add_requires_csrf(self, authenticated_client):
        """Add endpoint requires CSRF."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/add",
            data={"name": "Test", "amount": "100", "user_id": "1", "csrf_token": ""},
        )

        assert response.status_code == 403

    def test_edit_requires_csrf(self, authenticated_client):
        """Edit endpoint requires CSRF."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/1/edit",
            data={"name": "Test", "amount": "100", "user_id": "1", "csrf_token": ""},
        )

        assert response.status_code == 403

    def test_delete_requires_csrf(self, authenticated_client):
        """Delete endpoint requires CSRF."""
        client, _ = authenticated_client

        response = client.post(
            "/costs/1/delete",
            data={"csrf_token": ""},
        )

        assert response.status_code == 403


class TestDatabaseErrorHandling:
    """Tests for database error handling."""

    def test_add_handles_db_error(self, authenticated_client, mock_db_session, mock_users_form):
        """Add endpoint handles database errors gracefully."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "bot.web.costs.save_message",
                side_effect=Exception("Database error"),
            ):
                response = client.post(
                    "/costs/add",
                    data={
                        "name": "Test",
                        "amount": "100",
                        "user_id": "1",
                        "csrf_token": csrf_token,
                    },
                )

        assert response.status_code == 200
        assert "Ошибка сохранения" in response.text

    def test_edit_handles_db_error(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Edit endpoint handles database errors gracefully."""
        client, csrf_token = authenticated_client

        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.text = "Test 100"
        mock_message.user_id = 100
        mock_message.created_at = datetime.now()

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("bot.web.costs.get_message_by_id", return_value=mock_message),
                patch(
                    "bot.web.costs.update_message",
                    side_effect=Exception("Database error"),
                ),
            ):
                response = client.post(
                    "/costs/1/edit",
                    data={
                        "name": "Test",
                        "amount": "100",
                        "user_id": "100",
                        "csrf_token": csrf_token,
                    },
                )

        assert response.status_code == 200
        assert "Ошибка сохранения" in response.text

    def test_delete_handles_db_error(self, authenticated_client, mock_db_session):
        """Delete endpoint handles database errors gracefully."""
        client, csrf_token = authenticated_client

        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.user_id = 100

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("bot.web.costs.get_message_by_id", return_value=mock_message),
                patch(
                    "bot.web.costs.delete_message_by_id",
                    side_effect=Exception("Database error"),
                ),
            ):
                response = client.post(
                    "/costs/1/delete",
                    data={"csrf_token": csrf_token},
                    follow_redirects=False,
                )

        # Should redirect with error flash message
        assert response.status_code == 303


class TestPaginationValidation:
    """Tests for pagination parameter validation."""

    def test_negative_page_parameter(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Negative page parameter is handled."""
        client, _ = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_paginated = MagicMock()
            mock_paginated.items = []
            mock_paginated.total = 0
            mock_paginated.page = 1
            mock_paginated.per_page = 20
            mock_paginated.total_pages = 1

            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "bot.web.costs.get_all_costs_paginated",
                return_value=mock_paginated,
            ):
                response = client.get("/costs?page=-1")

        assert response.status_code == 200

    def test_zero_page_parameter(self, authenticated_client, mock_db_session, mock_get_all_users):
        """Zero page parameter is handled."""
        client, _ = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_paginated = MagicMock()
            mock_paginated.items = []
            mock_paginated.total = 0
            mock_paginated.page = 1
            mock_paginated.per_page = 20
            mock_paginated.total_pages = 1

            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "bot.web.costs.get_all_costs_paginated",
                return_value=mock_paginated,
            ):
                response = client.get("/costs?page=0")

        assert response.status_code == 200


class TestEdgeCasesApi:
    """Tests for edge cases in API."""

    def test_add_with_unicode_name(self, authenticated_client, mock_db_session, mock_users_form):
        """Add cost with unicode characters in name."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_message = MagicMock()
            mock_message.id = 1

            with patch(
                "bot.web.costs.save_message",
                return_value=mock_message,
            ):
                response = client.post(
                    "/costs/add",
                    data={
                        "name": "Кофе ☕ латте",
                        "amount": "350",
                        "user_id": "1",
                        "csrf_token": csrf_token,
                    },
                    follow_redirects=False,
                )

        assert response.status_code == 303

    def test_add_with_comma_decimal(self, authenticated_client, mock_db_session, mock_users_form):
        """Add cost with comma as decimal separator."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_message = MagicMock()
            mock_message.id = 1

            with patch(
                "bot.web.costs.save_message",
                return_value=mock_message,
            ):
                response = client.post(
                    "/costs/add",
                    data={
                        "name": "Test",
                        "amount": "100,50",
                        "user_id": "1",
                        "csrf_token": csrf_token,
                    },
                    follow_redirects=False,
                )

        assert response.status_code == 303

    def test_add_with_custom_date(self, authenticated_client, mock_db_session, mock_users_form):
        """Add cost with custom datetime."""
        client, csrf_token = authenticated_client

        with patch("bot.web.costs.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_db_session
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_message = MagicMock()
            mock_message.id = 1

            with patch(
                "bot.web.costs.save_message",
                return_value=mock_message,
            ):
                response = client.post(
                    "/costs/add",
                    data={
                        "name": "Test",
                        "amount": "100",
                        "user_id": "1",
                        "created_at": "2025-06-15",
                        "csrf_token": csrf_token,
                    },
                    follow_redirects=False,
                )

        assert response.status_code == 303
