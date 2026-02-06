"""Unit tests for auth routes (login/logout)."""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from bot.web.app import app
from bot.web.auth import SESSION_COOKIE, auth_sessions


def _make_user(id=1, telegram_id=123, name="Иван", role="user"):
    user = MagicMock()
    user.id = id
    user.telegram_id = telegram_id
    user.name = name
    user.role = role
    return user


@asynccontextmanager
async def _mock_db_session():
    yield AsyncMock()


class TestLoginPage:
    """Tests for GET /login."""

    @pytest.mark.asyncio
    async def test_returns_200_when_not_authenticated(self):
        """Login page returns 200 for unauthenticated users."""
        users = [_make_user(1, 123, "Иван", "user")]

        with (
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/login")

        assert response.status_code == 200
        assert "Пароль" in response.text
        assert "Пользователь" in response.text  # User dropdown label

    @pytest.mark.asyncio
    async def test_redirects_when_already_authenticated(self):
        """Authenticated user is redirected to /costs."""
        token = "auth-login-page-test"
        auth_sessions[token] = {"authenticated": True, "created_at": datetime.now(), "csrf_token": "x"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/login", cookies={SESSION_COOKIE: token}, follow_redirects=False)

        auth_sessions.pop(token, None)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]


class TestLoginPost:
    """Tests for POST /login."""

    @pytest.mark.asyncio
    async def test_login_with_correct_password(self):
        """Correct password and valid user creates session and redirects."""
        user = _make_user(1, 123, "Иван", "user")
        users = [user]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
            patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(return_value=user)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/login", data={"password": "secret", "user_id": "123"}, follow_redirects=False
                )

        assert response.status_code == 303
        assert "/costs" in response.headers["location"]
        assert SESSION_COOKIE in response.cookies

        # Verify session has user info
        session_token = response.cookies[SESSION_COOKIE]
        assert auth_sessions[session_token]["telegram_id"] == 123
        assert auth_sessions[session_token]["user_name"] == "Иван"
        assert auth_sessions[session_token]["role"] == "user"

        # Cleanup session
        auth_sessions.pop(session_token, None)

    @pytest.mark.asyncio
    async def test_login_with_wrong_password(self):
        """Wrong password returns login page with error."""
        users = [_make_user(1, 123, "Иван", "user")]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/login", data={"password": "wrong", "user_id": "123"})

        assert response.status_code == 200
        assert "Неверный пароль" in response.text

    @pytest.mark.asyncio
    async def test_login_with_invalid_user_id(self):
        """Invalid user_id returns login page with error."""
        users = [_make_user(1, 123, "Иван", "user")]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
            patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(return_value=None)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/login", data={"password": "secret", "user_id": "999"})

        assert response.status_code == 200
        assert "Пользователь не найден" in response.text

    @pytest.mark.asyncio
    async def test_login_when_password_not_configured(self):
        """Shows error when WEB_PASSWORD not set."""
        users = [_make_user(1, 123, "Иван", "user")]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            mock_settings.web_password = ""
            mock_settings.web_root_path = ""
            mock_settings.env = "test"

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/login", data={"password": "anything", "user_id": "123"})

        assert response.status_code == 200
        assert "Пароль не настроен" in response.text

    @pytest.mark.asyncio
    async def test_login_rate_limiting(self):
        """After MAX_LOGIN_ATTEMPTS failures, login is rate-limited."""
        from bot.web.auth import login_attempts, MAX_LOGIN_ATTEMPTS
        import time

        ip = "127.0.0.1"
        users = [_make_user(1, 123, "Иван", "user")]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"

            # Fill up rate limit
            login_attempts[ip] = [time.time() for _ in range(MAX_LOGIN_ATTEMPTS)]

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/login", data={"password": "wrong", "user_id": "123"})

        login_attempts.pop(ip, None)
        assert response.status_code == 200
        assert "Слишком много попыток" in response.text


    @pytest.mark.asyncio
    async def test_login_auto_promotes_admin_telegram_id(self):
        """User matching ADMIN_TELEGRAM_ID is auto-promoted to admin."""
        user = _make_user(1, 555, "Будущий Админ", "user")
        users = [user]

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db():
            yield mock_session

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=mock_db),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
            patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(return_value=user)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"
            mock_settings.admin_telegram_id = 555

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/login", data={"password": "secret", "user_id": "555"}, follow_redirects=False
                )

        assert response.status_code == 303
        # User role was updated
        assert user.role == "admin"
        mock_session.commit.assert_called_once()

        # Session stores admin role
        session_token = response.cookies[SESSION_COOKIE]
        assert auth_sessions[session_token]["role"] == "admin"
        auth_sessions.pop(session_token, None)

    @pytest.mark.asyncio
    async def test_login_no_promotion_without_admin_telegram_id(self):
        """Without ADMIN_TELEGRAM_ID, no auto-promotion happens."""
        user = _make_user(1, 123, "Иван", "user")
        users = [user]

        with (
            patch("bot.web.auth.settings") as mock_settings,
            patch("bot.web.auth.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.auth.get_all_users", new=AsyncMock(return_value=users)),
            patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(return_value=user)),
        ):
            mock_settings.web_password = "secret"
            mock_settings.web_root_path = ""
            mock_settings.env = "test"
            mock_settings.admin_telegram_id = None

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/login", data={"password": "secret", "user_id": "123"}, follow_redirects=False
                )

        assert response.status_code == 303
        assert user.role == "user"

        session_token = response.cookies[SESSION_COOKIE]
        assert auth_sessions[session_token]["role"] == "user"
        auth_sessions.pop(session_token, None)


class TestLogout:
    """Tests for GET /logout."""

    @pytest.mark.asyncio
    async def test_logout_deletes_session_and_redirects(self):
        """Logout removes session and redirects to /login."""
        token = "logout-test-session"
        auth_sessions[token] = {"authenticated": True, "created_at": datetime.now(), "csrf_token": "x"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/logout", cookies={SESSION_COOKIE: token}, follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]
        assert token not in auth_sessions

    @pytest.mark.asyncio
    async def test_logout_without_session_still_redirects(self):
        """Logout without active session still redirects cleanly."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestRootRedirect:
    """Tests for GET / root redirect."""

    @pytest.mark.asyncio
    async def test_root_redirects_to_costs(self):
        """Root / redirects to /costs."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/", follow_redirects=False)

        assert response.status_code == 307
        assert "/costs" in response.headers["location"]


class TestLogsRoute:
    """Tests for GET /logs."""

    @pytest.mark.asyncio
    async def test_logs_redirects_when_not_authenticated(self):
        """Unauthenticated request redirects to /login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/logs", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_logs_returns_200_when_admin(self):
        """Admin request returns logs placeholder page."""
        token = "logs-admin-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "x",
            "role": "admin",
            "telegram_id": 111,
            "user_name": "Админ",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/logs", cookies={SESSION_COOKIE: token})

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "Раздел пока не реализован" in response.text

    @pytest.mark.asyncio
    async def test_logs_redirects_non_admin_to_costs(self):
        """Non-admin user is redirected from /logs to /costs."""
        token = "logs-user-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "x",
            "role": "user",
            "telegram_id": 222,
            "user_name": "Пользователь",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/logs", cookies={SESSION_COOKIE: token}, follow_redirects=False)

        auth_sessions.pop(token, None)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]
