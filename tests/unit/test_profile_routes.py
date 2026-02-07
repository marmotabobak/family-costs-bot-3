"""Unit tests for profile routes (change-password)."""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from bot.security import hash_password
from bot.web.app import app
from bot.web.auth import SESSION_COOKIE, auth_sessions


def _make_user(id=1, telegram_id=123, name="Иван", role="user", password_hash=None):
    user = MagicMock()
    user.id = id
    user.telegram_id = telegram_id
    user.name = name
    user.role = role
    user.password_hash = password_hash
    return user


@asynccontextmanager
async def _mock_db_session():
    yield AsyncMock()


class TestChangePasswordForm:
    """Tests for GET /profile/change-password."""

    @pytest.mark.asyncio
    async def test_change_password_form_returns_200(self):
        """Authenticated user can access change password form."""
        token = "change-password-form-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/profile/change-password", cookies={SESSION_COOKIE: token})

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "Текущий пароль" in response.text
        assert "Новый пароль" in response.text

    @pytest.mark.asyncio
    async def test_change_password_form_redirects_unauthenticated(self):
        """Unauthenticated user is redirected to login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/profile/change-password", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestChangePasswordPost:
    """Tests for POST /profile/change-password."""

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        """Correct current password and valid new password changes password."""
        hashed = hash_password("old_password")
        user = _make_user(1, 123, "Иван", "user", password_hash=hashed)

        token = "change-password-success-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db():
            yield mock_session

        with (
            patch("bot.web.profile.get_db_session", side_effect=mock_db),
            patch("bot.web.profile.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("bot.web.profile.update_user_password", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/profile/change-password",
                    data={
                        "current_password": "old_password",
                        "new_password": "new_password",
                        "confirm_password": "new_password",
                        "csrf_token": "csrf123",
                    },
                    cookies={SESSION_COOKIE: token},
                    follow_redirects=False,
                )

        auth_sessions.pop(token, None)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self):
        """Wrong current password shows error."""
        hashed = hash_password("old_password")
        user = _make_user(1, 123, "Иван", "user", password_hash=hashed)

        token = "change-password-wrong-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        with (
            patch("bot.web.profile.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.profile.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/profile/change-password",
                    data={
                        "current_password": "wrong_password",
                        "new_password": "new_password",
                        "confirm_password": "new_password",
                        "csrf_token": "csrf123",
                    },
                    cookies={SESSION_COOKIE: token},
                )

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "Текущий пароль неверен" in response.text

    @pytest.mark.asyncio
    async def test_change_password_mismatch(self):
        """New password and confirm password mismatch shows error."""
        token = "change-password-mismatch-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/profile/change-password",
                data={
                    "current_password": "old_password",
                    "new_password": "new_password",
                    "confirm_password": "different_password",
                    "csrf_token": "csrf123",
                },
                cookies={SESSION_COOKIE: token},
            )

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "не совпадают" in response.text

    @pytest.mark.asyncio
    async def test_change_password_too_short(self):
        """New password shorter than 4 characters shows error."""
        token = "change-password-short-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/profile/change-password",
                data={
                    "current_password": "old_password",
                    "new_password": "abc",
                    "confirm_password": "abc",
                    "csrf_token": "csrf123",
                },
                cookies={SESSION_COOKIE: token},
            )

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "не менее 4 символов" in response.text

    @pytest.mark.asyncio
    async def test_change_password_csrf_required(self):
        """Missing CSRF token returns 403."""
        token = "change-password-csrf-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/profile/change-password",
                data={
                    "current_password": "old",
                    "new_password": "new",
                    "confirm_password": "new",
                    "csrf_token": "wrong_token",
                },
                cookies={SESSION_COOKIE: token},
            )

        auth_sessions.pop(token, None)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_change_password_user_without_hash(self):
        """User without password_hash shows error."""
        user = _make_user(1, 123, "Иван", "user", password_hash=None)

        token = "change-password-no-hash-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 1,
            "telegram_id": 123,
            "user_name": "Иван",
            "role": "user",
        }

        with (
            patch("bot.web.profile.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.profile.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/profile/change-password",
                    data={
                        "current_password": "old_password",
                        "new_password": "new_password",
                        "confirm_password": "new_password",
                        "csrf_token": "csrf123",
                    },
                    cookies={SESSION_COOKIE: token},
                )

        auth_sessions.pop(token, None)
        assert response.status_code == 200
        assert "Текущий пароль неверен" in response.text

    @pytest.mark.asyncio
    async def test_change_password_uses_user_id_from_session(self):
        """Change password uses user_id from session, not telegram_id."""
        hashed = hash_password("old_password")
        # User with specific DB id=42
        user = _make_user(42, 999, "Тест", "user", password_hash=hashed)

        token = "change-password-user-id-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "csrf123",
            "user_id": 42,  # DB id, not telegram_id
            "telegram_id": 999,
            "user_name": "Тест",
            "role": "user",
        }

        mock_session = AsyncMock()
        mock_get_user_by_id = AsyncMock(return_value=user)
        mock_update_password = AsyncMock(return_value=user)

        @asynccontextmanager
        async def mock_db():
            yield mock_session

        with (
            patch("bot.web.profile.get_db_session", side_effect=mock_db),
            patch("bot.web.profile.get_user_by_id", mock_get_user_by_id),
            patch("bot.web.profile.update_user_password", mock_update_password),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/profile/change-password",
                    data={
                        "current_password": "old_password",
                        "new_password": "new_password",
                        "confirm_password": "new_password",
                        "csrf_token": "csrf123",
                    },
                    cookies={SESSION_COOKIE: token},
                    follow_redirects=False,
                )

        auth_sessions.pop(token, None)
        assert response.status_code == 303
        # Verify get_user_by_id was called with DB id from session, not telegram_id
        mock_get_user_by_id.assert_called_once_with(mock_session, 42)
