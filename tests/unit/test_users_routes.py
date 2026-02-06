"""Unit tests for users management routes."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from bot.web.app import app
from bot.web.auth import auth_sessions


def _make_user(id=1, telegram_id=123, name="Иван", role="user"):
    user = MagicMock()
    user.id = id
    user.telegram_id = telegram_id
    user.name = name
    user.role = role
    user.created_at = MagicMock()
    user.created_at.strftime = MagicMock(return_value="01.01.2026 12:00")
    return user


@asynccontextmanager
async def _mock_db_session():
    yield AsyncMock()


def _setup_auth(role="admin", telegram_id=111, user_name="Админ"):
    """Create an authenticated session and return (token, csrf_token).

    Args:
        role: User role ('admin' or 'user')
        telegram_id: User's telegram ID
        user_name: User's display name
    """
    token = f"test-users-session-{role}"
    csrf = "test-users-csrf"
    from datetime import datetime

    auth_sessions[token] = {
        "authenticated": True,
        "created_at": datetime.now(),
        "csrf_token": csrf,
        "role": role,
        "telegram_id": telegram_id,
        "user_name": user_name,
    }
    return token, csrf


def _cleanup_auth(token):
    auth_sessions.pop(token, None)


class TestUsersListRoute:
    """Tests for GET /users."""

    @pytest.mark.asyncio
    async def test_redirects_to_login_when_not_authenticated(self):
        """Unauthenticated request redirects to /login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/users", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_returns_200_when_authenticated(self):
        """Authenticated request returns users list page."""
        token, _ = _setup_auth()
        users = [_make_user(1, 111, "Алёна"), _make_user(2, 222, "Иван")]

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_all_users", new=AsyncMock(return_value=users)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Алёна" in response.text
        assert "Иван" in response.text

    @pytest.mark.asyncio
    async def test_shows_empty_state_when_no_users(self):
        """Shows empty message when no users exist."""
        token, _ = _setup_auth()

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_all_users", new=AsyncMock(return_value=[])),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Пользователей нет" in response.text


class TestAddUserRoute:
    """Tests for GET/POST /users/add."""

    @pytest.mark.asyncio
    async def test_add_form_returns_200(self):
        """Add user form returns 200 when authenticated."""
        token, _ = _setup_auth()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/users/add", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Добавить пользователя" in response.text

    @pytest.mark.asyncio
    async def test_add_user_success(self):
        """Successful user creation redirects to /users."""
        token, csrf = _setup_auth()

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.create_user", new=AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/add",
                    cookies={"costs_session": token},
                    data={"name": "Новый", "telegram_id": "999", "csrf_token": csrf},
                    follow_redirects=False,
                )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/users" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_add_user_empty_name_shows_error(self):
        """Empty name shows validation error."""
        token, csrf = _setup_auth()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/add",
                cookies={"costs_session": token},
                data={"name": "  ", "telegram_id": "999", "csrf_token": csrf},
            )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Имя не может быть пустым" in response.text

    @pytest.mark.asyncio
    async def test_add_user_invalid_telegram_id_shows_error(self):
        """Non-numeric telegram_id shows validation error."""
        token, csrf = _setup_auth()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/add",
                cookies={"costs_session": token},
                data={"name": "Тест", "telegram_id": "abc", "csrf_token": csrf},
            )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Telegram ID должен быть числом" in response.text

    @pytest.mark.asyncio
    async def test_add_user_negative_telegram_id_shows_error(self):
        """Negative telegram_id shows validation error."""
        token, csrf = _setup_auth()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/add",
                cookies={"costs_session": token},
                data={"name": "Тест", "telegram_id": "-5", "csrf_token": csrf},
            )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Telegram ID должен быть больше 0" in response.text

    @pytest.mark.asyncio
    async def test_add_user_duplicate_telegram_id_shows_error(self):
        """Duplicate telegram_id shows IntegrityError message."""
        from sqlalchemy.exc import IntegrityError

        token, csrf = _setup_auth()

        async def raise_integrity(session, **kwargs):
            raise IntegrityError("duplicate", None, Exception("duplicate"))

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.create_user", side_effect=raise_integrity),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/add",
                    cookies={"costs_session": token},
                    data={"name": "Тест", "telegram_id": "123", "csrf_token": csrf},
                )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "уже существует" in response.text


class TestEditUserRoute:
    """Tests for GET/POST /users/{id}/edit."""

    @pytest.mark.asyncio
    async def test_edit_form_returns_200(self):
        """Edit form returns 200 with user data prefilled."""
        token, _ = _setup_auth()
        user = _make_user(1, 123, "Иван")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users/1/edit", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Иван" in response.text
        assert "123" in response.text

    @pytest.mark.asyncio
    async def test_edit_form_returns_404_when_not_found(self):
        """Edit form returns 404 for unknown user."""
        token, _ = _setup_auth()

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=None)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users/999/edit", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_user_success(self):
        """Successful edit redirects to /users."""
        token, csrf = _setup_auth()
        user = _make_user(1, 123, "Иван")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("bot.web.users.update_user", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/edit",
                    cookies={"costs_session": token},
                    data={"name": "Обновлённый", "telegram_id": "456", "csrf_token": csrf},
                    follow_redirects=False,
                )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/users" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_edit_user_empty_name_shows_error(self):
        """Edit with empty name re-renders form with error."""
        token, csrf = _setup_auth()
        user = _make_user(1, 123, "Иван")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/edit",
                    cookies={"costs_session": token},
                    data={"name": "  ", "telegram_id": "123", "csrf_token": csrf},
                )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Имя не может быть пустым" in response.text

    @pytest.mark.asyncio
    async def test_edit_user_invalid_telegram_id_shows_error(self):
        """Edit with non-numeric telegram_id returns error."""
        token, csrf = _setup_auth()
        user = _make_user(1, 123, "Иван")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/edit",
                    cookies={"costs_session": token},
                    data={"name": "Иван", "telegram_id": "xyz", "csrf_token": csrf},
                )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Telegram ID должен быть числом" in response.text

    @pytest.mark.asyncio
    async def test_edit_user_duplicate_telegram_id_shows_error(self):
        """Edit with a telegram_id already taken by another user shows error."""
        from sqlalchemy.exc import IntegrityError

        token, csrf = _setup_auth()
        user = _make_user(1, 123, "Иван")

        async def raise_integrity(*args, **kwargs):
            raise IntegrityError("duplicate", None, Exception("duplicate"))

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("bot.web.users.update_user", side_effect=raise_integrity),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/edit",
                    cookies={"costs_session": token},
                    data={"name": "Иван", "telegram_id": "999", "csrf_token": csrf},
                )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "уже существует" in response.text


class TestDeleteUserRoute:
    """Tests for POST /users/{id}/delete."""

    @pytest.mark.asyncio
    async def test_delete_user_success(self):
        """Successful delete redirects to /users."""
        token, csrf = _setup_auth()

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.delete_user", new=AsyncMock(return_value=True)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/delete",
                    cookies={"costs_session": token},
                    data={"csrf_token": csrf},
                    follow_redirects=False,
                )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/users" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self):
        """Returns 404 when user doesn't exist."""
        token, csrf = _setup_auth()

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.delete_user", new=AsyncMock(return_value=False)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/999/delete",
                    cookies={"costs_session": token},
                    data={"csrf_token": csrf},
                )

        _cleanup_auth(token)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_without_auth_redirects(self):
        """Unauthenticated delete request redirects to login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/1/delete",
                data={"csrf_token": "x"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestRoleBasedAccess:
    """Tests for admin-only access to users management."""

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_users_list(self):
        """Non-admin user is redirected from /users to /costs."""
        token, _ = _setup_auth(role="user", telegram_id=222, user_name="Обычный")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/users", cookies={"costs_session": token}, follow_redirects=False)

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_add_user(self):
        """Non-admin user is redirected from /users/add to /costs."""
        token, _ = _setup_auth(role="user", telegram_id=222, user_name="Обычный")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/users/add", cookies={"costs_session": token}, follow_redirects=False)

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_edit_user(self):
        """Non-admin user is redirected from /users/{id}/edit to /costs."""
        token, _ = _setup_auth(role="user", telegram_id=222, user_name="Обычный")
        user = _make_user(1, 123, "Иван", "user")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users/1/edit", cookies={"costs_session": token}, follow_redirects=False)

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_delete_user(self):
        """Non-admin user is redirected from delete action to /costs."""
        token, csrf = _setup_auth(role="user", telegram_id=222, user_name="Обычный")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/1/delete",
                cookies={"costs_session": token},
                data={"csrf_token": csrf},
                follow_redirects=False,
            )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/costs" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_admin_can_access_users_list(self):
        """Admin user can access /users."""
        token, _ = _setup_auth(role="admin", telegram_id=111, user_name="Админ")
        users = [_make_user(1, 111, "Админ", "admin"), _make_user(2, 222, "Пользователь", "user")]

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_all_users", new=AsyncMock(return_value=users)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Пользователи" in response.text

    @pytest.mark.asyncio
    async def test_users_list_shows_role_column(self):
        """Users list displays role column for each user."""
        token, _ = _setup_auth(role="admin", telegram_id=111, user_name="Админ")
        users = [_make_user(1, 111, "Админ", "admin"), _make_user(2, 222, "Пользователь", "user")]

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_all_users", new=AsyncMock(return_value=users)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/users", cookies={"costs_session": token})

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Роль" in response.text  # Header

    @pytest.mark.asyncio
    async def test_add_user_with_role(self):
        """Admin can add user with role."""
        token, csrf = _setup_auth(role="admin", telegram_id=111, user_name="Админ")
        new_user = _make_user(3, 333, "Новый", "user")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.create_user", new=AsyncMock(return_value=new_user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/add",
                    cookies={"costs_session": token},
                    data={"name": "Новый", "telegram_id": "333", "role": "admin", "csrf_token": csrf},
                    follow_redirects=False,
                )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/users" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_add_user_invalid_role_shows_error(self):
        """Invalid role shows validation error."""
        token, csrf = _setup_auth(role="admin", telegram_id=111, user_name="Админ")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/users/add",
                cookies={"costs_session": token},
                data={"name": "Тест", "telegram_id": "999", "role": "invalid_role", "csrf_token": csrf},
            )

        _cleanup_auth(token)
        assert response.status_code == 200
        assert "Некорректная роль" in response.text

    @pytest.mark.asyncio
    async def test_edit_user_with_role(self):
        """Admin can edit user role."""
        token, csrf = _setup_auth(role="admin", telegram_id=111, user_name="Админ")
        user = _make_user(1, 123, "Иван", "user")

        with (
            patch("bot.web.users.get_db_session", side_effect=_mock_db_session),
            patch("bot.web.users.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("bot.web.users.update_user", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/users/1/edit",
                    cookies={"costs_session": token},
                    data={"name": "Иван", "telegram_id": "123", "role": "admin", "csrf_token": csrf},
                    follow_redirects=False,
                )

        _cleanup_auth(token)
        assert response.status_code == 303
        assert "/users" in response.headers["location"]
