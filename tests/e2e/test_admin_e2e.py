"""E2E tests for admin panel — full user journey flows.

DB is mocked at the repository layer with a stateful in-memory store (FakeDB).
Auth sessions and import sessions are the real in-memory dicts, so cookie flow
and CSRF validation are exercised end-to-end.
"""

import io
import json
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from bot.web.app import app, import_sessions
from bot.web.auth import SESSION_COOKIE, auth_sessions, login_attempts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "e2e-test-pass"


@asynccontextmanager
async def _fake_session():
    """Yield a throwaway async-mock session (commit/rollback are no-ops)."""
    yield AsyncMock()


class FakeDB:
    """Stateful in-memory store that backs mocked repository functions."""

    def __init__(self):
        self.users: dict[int, MagicMock] = {}
        self.messages: dict[int, MagicMock] = {}
        self._next_uid = 1
        self._next_mid = 1

    # --- user repo ---

    def _make_user(self, uid, tid, name, role="user"):
        u = MagicMock()
        u.id = uid
        u.telegram_id = tid
        u.name = name
        u.role = role
        u.created_at = MagicMock()
        u.created_at.strftime = MagicMock(return_value="01.01.2026 12:00")
        return u

    async def get_all_users(self, session):
        return sorted(self.users.values(), key=lambda u: u.name)

    async def get_user_by_id(self, session, user_id):
        return self.users.get(user_id)

    async def get_user_by_telegram_id(self, session, telegram_id):
        for u in self.users.values():
            if u.telegram_id == telegram_id:
                return u
        return None

    async def create_user(self, session, telegram_id, name):
        for u in self.users.values():
            if u.telegram_id == telegram_id:
                raise IntegrityError("duplicate", None, Exception("duplicate"))
        uid = self._next_uid
        self._next_uid += 1
        self.users[uid] = self._make_user(uid, telegram_id, name)
        return self.users[uid]

    async def update_user(self, session, user_id, telegram_id, name, role=None):
        u = self.users.get(user_id)
        if not u:
            return None
        u.telegram_id = telegram_id
        u.name = name
        if role is not None:
            u.role = role
        return u

    async def delete_user(self, session, user_id):
        if user_id in self.users:
            del self.users[user_id]
            return True
        return False

    # --- messages repo ---

    def _make_msg(self, mid, user_id, text, created_at=None):
        m = MagicMock()
        m.id = mid
        m.user_id = user_id
        m.text = text
        m.created_at = created_at or datetime.now()
        return m

    async def get_all_costs_paginated(self, session, page=1, per_page=20, order_by="created_at", order_dir="desc"):
        items = list(self.messages.values())
        r = MagicMock()
        r.items = items
        r.total = len(items)
        r.page = page
        r.per_page = per_page
        r.total_pages = max(1, -(-len(items) // per_page))
        return r

    async def get_message_by_id(self, session, msg_id):
        return self.messages.get(msg_id)

    async def save_message(self, session, user_id, text, created_at=None):
        mid = self._next_mid
        self._next_mid += 1
        self.messages[mid] = self._make_msg(mid, user_id, text, created_at)
        return self.messages[mid]

    async def update_message(self, session, message_id, text, user_id, created_at=None):
        m = self.messages.get(message_id)
        if not m:
            return None
        m.text = text
        m.user_id = user_id
        if created_at:
            m.created_at = created_at
        return m

    async def delete_message_by_id(self, session, msg_id):
        if msg_id in self.messages:
            del self.messages[msg_id]
            return True
        return False

    async def get_all_messages(self, session):
        return list(self.messages.values())

    async def bulk_delete_messages(self, session, message_ids):
        count = 0
        for mid in message_ids:
            if mid in self.messages:
                del self.messages[mid]
                count += 1
        return count

    async def bulk_update_messages_date(self, session, message_ids, new_date):
        count = 0
        for mid in message_ids:
            if mid in self.messages:
                self.messages[mid].created_at = new_date
                count += 1
        return count

    async def bulk_update_messages_user(self, session, message_ids, new_user_id):
        count = 0
        for mid in message_ids:
            if mid in self.messages:
                self.messages[mid].user_id = new_user_id
                count += 1
        return count


SAMPLE_CHECKS = {
    "checks": [
        {
            "store": "VkusVill Москва",
            "date": "2026-01-15T10:30:00",
            "items": [
                {"name": "Молоко", "sum": 120.5},
                {"name": "Хлеб", "sum": 85.0},
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_auth_settings():
    """Make login work with a known password for all tests in this module."""
    with patch("bot.web.auth.settings") as mock:
        mock.web_password = _PASS
        mock.web_root_path = ""
        mock.env = "test"
        yield


@pytest.fixture(autouse=True)
def _cleanup_global_state():
    """Clear shared in-memory state after every test."""
    yield
    auth_sessions.clear()
    login_attempts.clear()
    import_sessions.clear()


@pytest.fixture
def db():
    fake = FakeDB()
    # Pre-seed default admin user for login
    fake.users[1] = fake._make_user(1, 100, "Тестовый Админ", role="admin")
    fake._next_uid = 2
    return fake


@pytest.fixture(autouse=True)
def auth_patches(db):
    """Patch auth module's DB calls so login can fetch users."""
    with (
        patch("bot.web.auth.get_db_session", side_effect=_fake_session),
        patch("bot.web.auth.get_all_users", new=AsyncMock(side_effect=db.get_all_users)),
        patch("bot.web.auth.get_user_by_telegram_id", new=AsyncMock(side_effect=db.get_user_by_telegram_id)),
    ):
        yield


@pytest.fixture
def users_patches(db):
    """Patch all users-route DB calls with FakeDB."""
    with (
        patch("bot.web.users.get_db_session", side_effect=_fake_session),
        patch("bot.web.users.get_all_users", new=AsyncMock(side_effect=db.get_all_users)),
        patch("bot.web.users.get_user_by_id", new=AsyncMock(side_effect=db.get_user_by_id)),
        patch("bot.web.users.create_user", new=AsyncMock(side_effect=db.create_user)),
        patch("bot.web.users.update_user", new=AsyncMock(side_effect=db.update_user)),
        patch("bot.web.users.delete_user", new=AsyncMock(side_effect=db.delete_user)),
    ):
        yield


@pytest.fixture
def costs_patches(db):
    """Patch all costs-route DB calls with FakeDB."""
    with (
        patch("bot.web.costs.get_db_session", side_effect=_fake_session),
        patch("bot.web.costs.get_all_costs_paginated", new=AsyncMock(side_effect=db.get_all_costs_paginated)),
        patch("bot.web.costs.get_all_messages", new=AsyncMock(side_effect=db.get_all_messages)),
        patch("bot.web.costs.get_message_by_id", new=AsyncMock(side_effect=db.get_message_by_id)),
        patch("bot.web.costs.save_message", new=AsyncMock(side_effect=db.save_message)),
        patch("bot.web.costs.update_message", new=AsyncMock(side_effect=db.update_message)),
        patch("bot.web.costs.delete_message_by_id", new=AsyncMock(side_effect=db.delete_message_by_id)),
        patch("bot.web.costs.bulk_delete_messages", new=AsyncMock(side_effect=db.bulk_delete_messages)),
        patch("bot.web.costs.bulk_update_messages_date", new=AsyncMock(side_effect=db.bulk_update_messages_date)),
        patch("bot.web.costs.bulk_update_messages_user", new=AsyncMock(side_effect=db.bulk_update_messages_user)),
        patch("bot.web.costs.get_all_users", new=AsyncMock(side_effect=db.get_all_users)),
    ):
        yield


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, telegram_id: int = 100) -> str:
    """POST /login as a specific user and return the CSRF token.

    Default telegram_id=100 corresponds to the pre-seeded admin user.
    """
    resp = await client.post(
        "/login",
        data={"password": _PASS, "user_id": str(telegram_id)},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"Login failed: {resp.text}"
    token = client.cookies[SESSION_COOKIE]
    return auth_sessions[token]["csrf_token"]


async def _login_as_user(client: AsyncClient, db: FakeDB, telegram_id: int, name: str) -> str:
    """Create a regular user in FakeDB and log in as them. Returns CSRF token."""
    # Check if user already exists
    existing = None
    for u in db.users.values():
        if u.telegram_id == telegram_id:
            existing = u
            break
    if not existing:
        uid = db._next_uid
        db._next_uid += 1
        db.users[uid] = db._make_user(uid, telegram_id, name, role="user")
    return await _login(client, telegram_id)


# ===========================================================================
# 1. Auth Journey
# ===========================================================================


class TestAuthJourney:
    """Login, session persistence, rate-limiting, and logout flows."""

    @pytest.mark.asyncio
    async def test_root_redirects_to_costs(self):
        """GET / returns 307 to /costs."""
        async with _client() as c:
            r = await c.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert "/costs" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_unauthenticated_costs_redirects_to_login(self):
        """GET /costs without session cookie redirects to /login."""
        async with _client() as c:
            r = await c.get("/costs", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_login_sets_session_cookie(self):
        """Successful login places costs_session cookie in client jar."""
        async with _client() as c:
            await _login(c)
            assert SESSION_COOKIE in c.cookies

    @pytest.mark.asyncio
    async def test_session_persists_to_logs(self):
        """Cookie set at login carries to a subsequent GET /logs."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/logs")
        assert r.status_code == 200
        assert "Раздел пока не реализован" in r.text

    @pytest.mark.asyncio
    async def test_wrong_then_correct_password(self):
        """A wrong password attempt does not prevent a correct one."""
        async with _client() as c:
            r = await c.post("/login", data={"password": "nope", "user_id": "100"})
            assert "Неверный пароль" in r.text
            # Correct password still works
            await _login(c)
            r = await c.get("/logs")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_max_attempts(self):
        """5 failed logins from same IP trigger rate-limit message."""
        from bot.web.auth import MAX_LOGIN_ATTEMPTS

        async with _client() as c:
            for _ in range(MAX_LOGIN_ATTEMPTS):
                await c.post("/login", data={"password": "bad", "user_id": "100"})
            r = await c.post("/login", data={"password": "bad", "user_id": "100"})
        assert "Слишком много попыток" in r.text

    @pytest.mark.asyncio
    async def test_logout_invalidates_session(self):
        """After GET /logout the session is gone; /logs redirects."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/logs")
            assert r.status_code == 200

            await c.get("/logout", follow_redirects=False)

            # Session gone — next request redirects
            r = await c.get("/logs", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]


# ===========================================================================
# 2. Users CRUD Journey
# ===========================================================================


class TestUsersCRUDJourney:
    """Create → list → edit → delete flows for users."""

    @pytest.mark.asyncio
    async def test_add_user_appears_in_list(self, users_patches, db):
        """Add a user, then verify name and ID appear in list."""
        async with _client() as c:
            csrf = await _login(c)

            # Add user
            r = await c.post(
                "/users/add",
                data={"name": "Алёна", "telegram_id": "111", "csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            # User now visible
            r = await c.get("/users")
        assert "Алёна" in r.text
        assert "111" in r.text

    @pytest.mark.asyncio
    async def test_edit_user_updates_data(self, users_patches, db):
        """Pre-seed a user, edit it, verify changes in list."""
        async with _client() as c:
            csrf = await _login(c)
            await db.create_user(None, 300, "Старый")
            uid = max(db.users.keys())  # Get the id of newly created user

            r = await c.post(
                f"/users/{uid}/edit",
                data={"name": "Новый", "telegram_id": "200", "csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/users")
        assert "Новый" in r.text
        assert "200" in r.text

    @pytest.mark.asyncio
    async def test_delete_user_removes_from_list(self, users_patches, db):
        """Pre-seed a user, delete it, verify it's gone from list."""
        async with _client() as c:
            csrf = await _login(c)
            await db.create_user(None, 300, "Удалимый")
            uid = max(db.users.keys())

            r = await c.post(
                f"/users/{uid}/delete",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/users")
        assert "Удалимый" not in r.text

    @pytest.mark.asyncio
    async def test_validation_empty_name(self, users_patches, db):
        """Empty/whitespace name returns form with error message."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post(
                "/users/add",
                data={"name": "   ", "telegram_id": "111", "csrf_token": csrf},
            )
        assert r.status_code == 200
        assert "Имя не может быть пустым" in r.text

    @pytest.mark.asyncio
    async def test_validation_non_numeric_telegram_id(self, users_patches, db):
        """Non-numeric telegram_id returns appropriate error."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post(
                "/users/add",
                data={"name": "Тест", "telegram_id": "abc", "csrf_token": csrf},
            )
        assert "Telegram ID должен быть числом" in r.text

    @pytest.mark.asyncio
    async def test_validation_zero_telegram_id(self, users_patches, db):
        """telegram_id ≤ 0 returns error."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post(
                "/users/add",
                data={"name": "Тест", "telegram_id": "0", "csrf_token": csrf},
            )
        assert "Telegram ID должен быть больше 0" in r.text

    @pytest.mark.asyncio
    async def test_duplicate_telegram_id_shows_error(self, users_patches, db):
        """Adding a second user with the same telegram_id shows error."""
        async with _client() as c:
            csrf = await _login(c)
            # First add succeeds
            await c.post(
                "/users/add",
                data={"name": "Первый", "telegram_id": "999", "csrf_token": csrf},
                follow_redirects=False,
            )
            # Second with same ID
            r = await c.post(
                "/users/add",
                data={"name": "Второй", "telegram_id": "999", "csrf_token": csrf},
            )
        assert "уже существует" in r.text

    @pytest.mark.asyncio
    async def test_edit_validation_empty_name(self, users_patches, db):
        """Edit with empty name re-renders form with error."""
        async with _client() as c:
            csrf = await _login(c)
            await db.create_user(None, 300, "Иван")
            uid = max(db.users.keys())

            r = await c.post(
                f"/users/{uid}/edit",
                data={"name": "  ", "telegram_id": "300", "csrf_token": csrf},
            )
        assert r.status_code == 200
        assert "Имя не может быть пустым" in r.text

    @pytest.mark.asyncio
    async def test_edit_nonexistent_user_returns_404(self, users_patches, db):
        """GET /users/999/edit when user 999 doesn't exist → 404."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/users/999/edit")
        assert r.status_code == 404


# ===========================================================================
# 3. Costs CRUD Journey
# ===========================================================================


class TestCostsCRUDJourney:
    """Create → list → edit → delete flows for costs."""

    @pytest.mark.asyncio
    async def test_add_cost_appears_in_list(self, costs_patches, db):
        """Add a cost entry, verify its name shows in the list."""
        async with _client() as c:
            csrf = await _login(c)

            r = await c.post(
                "/costs/add",
                data={
                    "name": "Молоко",
                    "amount": "99.50",
                    "user_id": "123",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/costs")
        assert "Молоко" in r.text

    @pytest.mark.asyncio
    async def test_edit_cost_updates_text(self, costs_patches, db):
        """Pre-seed a message, edit name+amount, verify in list."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Старое 50")

            r = await c.post(
                "/costs/1/edit",
                data={
                    "name": "Новое",
                    "amount": "75",
                    "user_id": "1",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/costs")
        assert "Новое" in r.text

    @pytest.mark.asyncio
    async def test_delete_cost_removes_from_list(self, costs_patches, db):
        """Pre-seed a message, delete it, verify it's gone from list."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Удалимый 10")

            r = await c.post(
                "/costs/1/delete",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/costs")
        assert "Удалимый" not in r.text

    @pytest.mark.asyncio
    async def test_invalid_amount_shows_error(self, costs_patches, db):
        """Non-numeric amount field returns validation error."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post(
                "/costs/add",
                data={
                    "name": "X",
                    "amount": "not-a-number",
                    "user_id": "1",
                    "csrf_token": csrf,
                },
            )
        assert "Некорректная сумма" in r.text

    @pytest.mark.asyncio
    async def test_invalid_user_id_shows_error(self, costs_patches, db):
        """user_id ≤ 0 on add-cost returns validation error."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post(
                "/costs/add",
                data={
                    "name": "Тест",
                    "amount": "10",
                    "user_id": "0",
                    "csrf_token": csrf,
                },
            )
        assert "User ID должен быть больше 0" in r.text

    @pytest.mark.asyncio
    async def test_edit_cost_invalid_amount_shows_error(self, costs_patches, db):
        """Edit with bad amount keeps form on screen with error."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Старое 50")

            r = await c.post(
                "/costs/1/edit",
                data={
                    "name": "Тест",
                    "amount": "abc",
                    "user_id": "1",
                    "csrf_token": csrf,
                },
            )
        assert "Некорректная сумма" in r.text

    @pytest.mark.asyncio
    async def test_edit_nonexistent_cost_returns_404(self, costs_patches, db):
        """GET /costs/999/edit when no such message → 404."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/costs/999/edit")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_cost_returns_404(self, costs_patches, db):
        """POST /costs/999/delete when no such message → 404."""
        async with _client() as c:
            csrf = await _login(c)
            r = await c.post("/costs/999/delete", data={"csrf_token": csrf})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_delete_removes_selected(self, costs_patches, db):
        """Select two costs and bulk-delete; only the unselected one remains."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Первый 10")
            await db.save_message(None, user_id=1, text="Второй 20")
            await db.save_message(None, user_id=1, text="Третий 30")

            r = await c.post(
                "/costs/bulk-delete",
                data={"ids": ["1", "2"], "csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/costs")
        assert "Первый" not in r.text
        assert "Второй" not in r.text
        assert "Третий" in r.text

    @pytest.mark.asyncio
    async def test_bulk_delete_csrf_required(self, costs_patches, db):
        """Bulk delete without valid CSRF → 403."""
        async with _client() as c:
            await _login(c)
            r = await c.post(
                "/costs/bulk-delete",
                data={"ids": ["1"], "csrf_token": "bad"},
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_change_date_updates_and_redirects(self, costs_patches, db):
        """Bulk date change redirects on success."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Тест 50")

            r = await c.post(
                "/costs/bulk-change-date",
                data={"ids": ["1"], "new_date": "2025-06-15", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_bulk_change_date_invalid_date_redirects(self, costs_patches, db):
        """Bulk date change with invalid date shows error flash."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Тест 50")

            r = await c.post(
                "/costs/bulk-change-date",
                data={"ids": ["1"], "new_date": "not-a-date", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_bulk_change_user_updates_and_redirects(self, costs_patches, db):
        """Bulk user change redirects on success and updates user_id."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Тест 50")
            await db.create_user(None, telegram_id=2, name="Второй")

            r = await c.post(
                "/costs/bulk-change-user",
                data={"ids": ["1"], "new_user_id": "2", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303
        # Verify user was updated in DB
        assert db.messages[1].user_id == 2

    @pytest.mark.asyncio
    async def test_bulk_change_user_invalid_user_redirects(self, costs_patches, db):
        """Bulk user change with invalid user_id shows error flash."""
        async with _client() as c:
            csrf = await _login(c)
            await db.save_message(None, user_id=1, text="Тест 50")

            r = await c.post(
                "/costs/bulk-change-user",
                data={"ids": ["1"], "new_user_id": "0", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_bulk_change_user_csrf_required(self, costs_patches, db):
        """Bulk user change without valid CSRF → 403."""
        async with _client() as c:
            await _login(c)
            r = await c.post(
                "/costs/bulk-change-user",
                data={"ids": ["1"], "new_user_id": "2", "csrf_token": "bad"},
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_filter_by_name_shows_matching(self, costs_patches, db):
        """Filter by name shows only matching costs."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Молоко 100")
            await db.save_message(None, user_id=1, text="Хлеб 50")
            await db.save_message(None, user_id=1, text="Молоко обезжиренное 200")

            r = await c.get("/costs?filter_name=молоко")
        assert "Молоко" in r.text
        assert "обезжиренное" in r.text
        assert "Хлеб" not in r.text

    @pytest.mark.asyncio
    async def test_filter_by_user_shows_only_user_costs(self, costs_patches, db):
        """Filter by user_id shows only that user's costs."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Пользователь1 100")
            await db.save_message(None, user_id=2, text="Пользователь2 200")

            r = await c.get("/costs?filter_user_id=1")
        assert "Пользователь1" in r.text
        assert "Пользователь2" not in r.text

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, costs_patches, db):
        """Filter by date range shows costs within range."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Январь 100", created_at=datetime(2026, 1, 15))
            await db.save_message(None, user_id=1, text="Февраль 200", created_at=datetime(2026, 2, 15))
            await db.save_message(None, user_id=1, text="Март 300", created_at=datetime(2026, 3, 15))

            r = await c.get("/costs?filter_date_from=2026-02-01&filter_date_to=2026-02-28")
        assert "Февраль" in r.text
        assert "Январь" not in r.text
        assert "Март" not in r.text

    @pytest.mark.asyncio
    async def test_filter_by_amount_range(self, costs_patches, db):
        """Filter by amount range shows costs within range."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Дешёвое 50")
            await db.save_message(None, user_id=1, text="Среднее 150")
            await db.save_message(None, user_id=1, text="Дорогое 300")

            r = await c.get("/costs?filter_amount_from=100&filter_amount_to=200")
        assert "Среднее" in r.text
        assert "Дешёвое" not in r.text
        assert "Дорогое" not in r.text

    @pytest.mark.asyncio
    async def test_filter_combined(self, costs_patches, db):
        """Multiple filters can be combined."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Молоко дорогое 200")
            await db.save_message(None, user_id=1, text="Молоко дешёвое 50")
            await db.save_message(None, user_id=2, text="Молоко другой 200")

            r = await c.get("/costs?filter_name=молоко&filter_user_id=1&filter_amount_from=100")
        assert "Молоко дорогое" in r.text
        assert "Молоко дешёвое" not in r.text
        assert "Молоко другой" not in r.text

    @pytest.mark.asyncio
    async def test_filter_shows_reset_button(self, costs_patches, db):
        """When filters are active, reset button is shown."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Тест 100")

            r = await c.get("/costs?filter_name=тест")
        assert "Сброс" in r.text
        assert "(отфильтровано)" in r.text

    # --- Filter edge case tests ---

    @pytest.mark.asyncio
    async def test_filter_empty_user_id_shows_all(self, costs_patches, db):
        """Empty filter_user_id (selecting 'Все') shows all costs without error."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Пользователь1 100")
            await db.save_message(None, user_id=2, text="Пользователь2 200")

            # Empty string should not cause int parsing error
            r = await c.get("/costs?filter_user_id=")
        assert r.status_code == 200
        assert "Пользователь1" in r.text
        assert "Пользователь2" in r.text

    @pytest.mark.asyncio
    async def test_filter_invalid_user_id_ignored(self, costs_patches, db):
        """Non-numeric filter_user_id is ignored (shows all costs)."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Пользователь1 100")
            await db.save_message(None, user_id=2, text="Пользователь2 200")

            r = await c.get("/costs?filter_user_id=abc")
        assert r.status_code == 200
        assert "Пользователь1" in r.text
        assert "Пользователь2" in r.text

    @pytest.mark.asyncio
    async def test_filter_invalid_date_from_ignored(self, costs_patches, db):
        """Invalid date_from format is ignored (shows all costs)."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Январь 100", created_at=datetime(2026, 1, 15))
            await db.save_message(None, user_id=1, text="Февраль 200", created_at=datetime(2026, 2, 15))

            r = await c.get("/costs?filter_date_from=not-a-date")
        assert r.status_code == 200
        assert "Январь" in r.text
        assert "Февраль" in r.text

    @pytest.mark.asyncio
    async def test_filter_invalid_date_to_ignored(self, costs_patches, db):
        """Invalid date_to format is ignored (shows all costs)."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Январь 100", created_at=datetime(2026, 1, 15))
            await db.save_message(None, user_id=1, text="Февраль 200", created_at=datetime(2026, 2, 15))

            r = await c.get("/costs?filter_date_to=invalid")
        assert r.status_code == 200
        assert "Январь" in r.text
        assert "Февраль" in r.text

    @pytest.mark.asyncio
    async def test_filter_invalid_amount_from_ignored(self, costs_patches, db):
        """Invalid amount_from is ignored (shows all costs)."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Дешёвое 50")
            await db.save_message(None, user_id=1, text="Дорогое 300")

            r = await c.get("/costs?filter_amount_from=xyz")
        assert r.status_code == 200
        assert "Дешёвое" in r.text
        assert "Дорогое" in r.text

    @pytest.mark.asyncio
    async def test_filter_invalid_amount_to_ignored(self, costs_patches, db):
        """Invalid amount_to is ignored (shows all costs)."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Дешёвое 50")
            await db.save_message(None, user_id=1, text="Дорогое 300")

            r = await c.get("/costs?filter_amount_to=abc")
        assert r.status_code == 200
        assert "Дешёвое" in r.text
        assert "Дорогое" in r.text

    @pytest.mark.asyncio
    async def test_filter_only_date_from(self, costs_patches, db):
        """Filter with only date_from shows costs from that date onwards."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Январь 100", created_at=datetime(2026, 1, 15))
            await db.save_message(None, user_id=1, text="Февраль 200", created_at=datetime(2026, 2, 15))

            r = await c.get("/costs?filter_date_from=2026-02-01")
        assert "Февраль" in r.text
        assert "Январь" not in r.text

    @pytest.mark.asyncio
    async def test_filter_only_date_to(self, costs_patches, db):
        """Filter with only date_to shows costs up to that date."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Январь 100", created_at=datetime(2026, 1, 15))
            await db.save_message(None, user_id=1, text="Февраль 200", created_at=datetime(2026, 2, 15))

            r = await c.get("/costs?filter_date_to=2026-01-31")
        assert "Январь" in r.text
        assert "Февраль" not in r.text

    @pytest.mark.asyncio
    async def test_filter_only_amount_from(self, costs_patches, db):
        """Filter with only amount_from shows costs >= that amount."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Дешёвое 50")
            await db.save_message(None, user_id=1, text="Дорогое 300")

            r = await c.get("/costs?filter_amount_from=100")
        assert "Дорогое" in r.text
        assert "Дешёвое" not in r.text

    @pytest.mark.asyncio
    async def test_filter_only_amount_to(self, costs_patches, db):
        """Filter with only amount_to shows costs <= that amount."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Дешёвое 50")
            await db.save_message(None, user_id=1, text="Дорогое 300")

            r = await c.get("/costs?filter_amount_to=100")
        assert "Дешёвое" in r.text
        assert "Дорогое" not in r.text

    @pytest.mark.asyncio
    async def test_filter_no_filters_shows_all(self, costs_patches, db):
        """No filters shows all costs."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Первый 100")
            await db.save_message(None, user_id=2, text="Второй 200")

            r = await c.get("/costs")
        assert r.status_code == 200
        assert "Первый" in r.text
        assert "Второй" in r.text

    @pytest.mark.asyncio
    async def test_filter_empty_result(self, costs_patches, db):
        """Filter that matches nothing shows empty state."""
        async with _client() as c:
            await _login(c)
            await db.save_message(None, user_id=1, text="Молоко 100")

            r = await c.get("/costs?filter_name=несуществующий")
        assert r.status_code == 200
        assert "Молоко" not in r.text


# ===========================================================================
# 4. Import Journey
# ===========================================================================


class TestImportJourney:
    """Token-based VkusVill import flow."""

    @pytest.mark.asyncio
    async def test_full_import_flow(self):
        """Happy path: create token → upload → select → save → success."""
        with (
            patch("bot.web.app.get_db_session", side_effect=_fake_session),
            patch("bot.web.app.save_message", new=AsyncMock()),
        ):
            async with _client() as c:
                # Generate import token
                r = await c.get("/dev/create-token/42")
                assert r.status_code == 200
                token = r.json()["token"]

                # Upload page accessible
                r = await c.get(f"/import/{token}")
                assert r.status_code == 200

                # Upload JSON
                payload = json.dumps(SAMPLE_CHECKS).encode("utf-8")
                r = await c.post(
                    f"/import/{token}/upload",
                    files={"file": ("checks.json", io.BytesIO(payload), "application/json")},
                    follow_redirects=False,
                )
                assert r.status_code == 303
                assert "/select" in r.headers["location"]

                # Select page lists items
                r = await c.get(f"/import/{token}/select")
                assert r.status_code == 200
                assert "Молоко" in r.text
                assert "Хлеб" in r.text

                # Save both items
                r = await c.post(
                    f"/import/{token}/save",
                    data={"items": ["0:0", "0:1"]},
                )
        assert r.status_code == 200
        assert "2" in r.text  # saved_count shown on success page

    @pytest.mark.asyncio
    async def test_invalid_token_returns_404(self):
        """All import sub-routes return 404 for an unknown token."""
        async with _client() as c:
            r = await c.get("/import/bad-token")
            assert r.status_code == 404

            r = await c.post(
                "/import/bad-token/upload",
                files={"file": ("x.json", io.BytesIO(b"{}"), "application/json")},
            )
            assert r.status_code == 404

            r = await c.get("/import/bad-token/select")
            assert r.status_code == 404

            r = await c.post("/import/bad-token/save", data={})
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_select_before_upload_redirects(self):
        """GET /select on a fresh token (no data uploaded) → redirect to upload."""
        async with _client() as c:
            r = await c.get("/dev/create-token/1")
            token = r.json()["token"]

            r = await c.get(f"/import/{token}/select", follow_redirects=False)
        assert r.status_code == 307

    @pytest.mark.asyncio
    async def test_save_empty_selection_shows_error(self):
        """POST /save with no items selected shows error on select page."""
        async with _client() as c:
            r = await c.get("/dev/create-token/1")
            token = r.json()["token"]

            # Upload first
            payload = json.dumps(SAMPLE_CHECKS).encode("utf-8")
            await c.post(
                f"/import/{token}/upload",
                files={"file": ("checks.json", io.BytesIO(payload), "application/json")},
            )

            # Save with no items
            r = await c.post(f"/import/{token}/save", data={})
        assert "Выберите хотя бы один товар" in r.text

    @pytest.mark.asyncio
    async def test_upload_invalid_json_shows_error(self):
        """Non-JSON file content shows parse error on upload page."""
        async with _client() as c:
            r = await c.get("/dev/create-token/1")
            token = r.json()["token"]

            r = await c.post(
                f"/import/{token}/upload",
                files={"file": ("bad.json", io.BytesIO(b"not json at all"), "application/json")},
            )
        assert r.status_code == 200
        assert "Ошибка чтения файла" in r.text

    @pytest.mark.asyncio
    async def test_upload_missing_checks_key_shows_error(self):
        """Valid JSON without 'checks' key shows format error."""
        async with _client() as c:
            r = await c.get("/dev/create-token/1")
            token = r.json()["token"]

            payload = json.dumps({"other": []}).encode("utf-8")
            r = await c.post(
                f"/import/{token}/upload",
                files={"file": ("bad.json", io.BytesIO(payload), "application/json")},
            )
        assert "Неверный формат файла" in r.text


# ===========================================================================
# 5. Security Scenarios
# ===========================================================================


class TestSecurityScenarios:
    """Cross-cutting security guards."""

    @pytest.mark.asyncio
    async def test_csrf_missing_returns_403(self, users_patches, db):
        """POST /users/add with empty csrf_token → 403."""
        async with _client() as c:
            await _login(c)
            r = await c.post(
                "/users/add",
                data={"name": "X", "telegram_id": "1", "csrf_token": ""},
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_csrf_tampered_returns_403(self, users_patches, db):
        """POST /users/add with a wrong csrf_token → 403."""
        async with _client() as c:
            await _login(c)
            r = await c.post(
                "/users/add",
                data={"name": "X", "telegram_id": "1", "csrf_token": "tampered-token"},
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_all_admin_routes_require_auth(self):
        """Every protected admin GET redirects to /login without a cookie."""
        async with _client() as c:
            for path in ["/costs", "/users", "/logs", "/users/add", "/costs/add"]:
                r = await c.get(path, follow_redirects=False)
                assert r.status_code == 303, f"{path} did not redirect"
                assert "/login" in r.headers["location"], f"{path} bad redirect"

    @pytest.mark.asyncio
    async def test_import_token_isolation(self):
        """Data uploaded via Token A is not visible through Token B."""
        async with _client() as c:
            r_a = await c.get("/dev/create-token/1")
            token_a = r_a.json()["token"]

            r_b = await c.get("/dev/create-token/2")
            token_b = r_b.json()["token"]

            # Upload to A
            payload = json.dumps(SAMPLE_CHECKS).encode("utf-8")
            await c.post(
                f"/import/{token_a}/upload",
                files={"file": ("c.json", io.BytesIO(payload), "application/json")},
            )

            # B has no data → select redirects back to upload
            r = await c.get(f"/import/{token_b}/select", follow_redirects=False)
        assert r.status_code == 307


# ===========================================================================
# 6. Navigation & Health
# ===========================================================================


class TestNavigationAndHealth:
    """UI structural checks and the health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok_without_auth(self):
        """GET /health is public and returns the expected JSON."""
        async with _client() as c:
            r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_nav_links_present_on_authenticated_page(self):
        """An authenticated page (logs) includes all primary nav links."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/logs")
        assert "/costs" in r.text
        assert "/users" in r.text
        assert "/logs" in r.text
        assert "/logout" in r.text

    @pytest.mark.asyncio
    async def test_already_authenticated_login_redirects(self):
        """GET /login when already logged in redirects to /costs."""
        async with _client() as c:
            await _login(c)
            r = await c.get("/login", follow_redirects=False)
        assert r.status_code == 303
        assert "/costs" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_nav_hides_users_and_logs(self, db, costs_patches):
        """Non-admin user sees costs link but not users/logs in nav."""
        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/costs")
        assert "/costs" in r.text
        assert "/users" not in r.text
        assert "/logs" not in r.text
        assert "/logout" in r.text


# ===========================================================================
# 7. Role-Based Access
# ===========================================================================


class TestRoleBasedAccessE2E:
    """E2E tests for admin vs user role permissions."""

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_users(self, db):
        """Non-admin accessing /users gets redirected to /costs."""
        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/users", follow_redirects=False)
        assert r.status_code == 303
        assert "/costs" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_redirected_from_logs(self, db):
        """Non-admin accessing /logs gets redirected to /costs."""
        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/logs", follow_redirects=False)
        assert r.status_code == 303
        assert "/costs" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_can_see_all_costs(self, db, costs_patches):
        """Non-admin can see all costs including other users'."""
        await db.save_message(None, user_id=100, text="Админский 50")
        await db.save_message(None, user_id=200, text="Пользовательский 75")

        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/costs")
        assert r.status_code == 200
        assert "Админский" in r.text
        assert "Пользовательский" in r.text

    @pytest.mark.asyncio
    async def test_non_admin_can_edit_own_cost(self, db, costs_patches):
        """Non-admin can edit their own cost."""
        await db.save_message(None, user_id=200, text="Своё 50")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")

            r = await c.get("/costs/1/edit")
            assert r.status_code == 200

            r = await c.post(
                "/costs/1/edit",
                data={
                    "name": "Обновлённое",
                    "amount": "75",
                    "user_id": "200",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_non_admin_cannot_edit_others_cost(self, db, costs_patches):
        """Non-admin is rejected when trying to edit another user's cost."""
        await db.save_message(None, user_id=100, text="Чужое 50")

        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/costs/1/edit", follow_redirects=False)
        assert r.status_code == 303
        assert "/costs" in r.headers["location"]

    @pytest.mark.asyncio
    async def test_non_admin_can_delete_own_cost(self, db, costs_patches):
        """Non-admin can delete their own cost."""
        await db.save_message(None, user_id=200, text="Своё 50")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/1/delete",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            r = await c.get("/costs")
        assert "Своё" not in r.text

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_others_cost(self, db, costs_patches):
        """Non-admin is rejected when trying to delete another user's cost."""
        await db.save_message(None, user_id=100, text="Чужое 50")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/1/delete",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            # Cost still exists
            r = await c.get("/costs")
        assert "Чужое" in r.text

    @pytest.mark.asyncio
    async def test_non_admin_bulk_delete_own_costs_ok(self, db, costs_patches):
        """Non-admin can bulk delete their own costs."""
        await db.save_message(None, user_id=200, text="Своё1 10")
        await db.save_message(None, user_id=200, text="Своё2 20")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/bulk-delete",
                data={"ids": ["1", "2"], "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_non_admin_bulk_delete_others_costs_rejected(self, db, costs_patches):
        """Non-admin cannot bulk delete when selection includes others' costs."""
        await db.save_message(None, user_id=200, text="Своё 10")
        await db.save_message(None, user_id=100, text="Чужое 20")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/bulk-delete",
                data={"ids": ["1", "2"], "csrf_token": csrf},
                follow_redirects=False,
            )
            assert r.status_code == 303

            # Both costs should still exist
            r = await c.get("/costs")
        assert "Своё" in r.text
        assert "Чужое" in r.text

    @pytest.mark.asyncio
    async def test_non_admin_bulk_change_date_own_ok(self, db, costs_patches):
        """Non-admin can bulk change date for own costs."""
        await db.save_message(None, user_id=200, text="Своё 10")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/bulk-change-date",
                data={"ids": ["1"], "new_date": "2026-06-01", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_non_admin_bulk_change_date_others_rejected(self, db, costs_patches):
        """Non-admin cannot bulk change date when selection includes others' costs."""
        await db.save_message(None, user_id=100, text="Чужое 50")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/bulk-change-date",
                data={"ids": ["1"], "new_date": "2026-06-01", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_non_admin_cannot_bulk_change_user(self, db, costs_patches):
        """Non-admin is rejected from bulk change user."""
        await db.save_message(None, user_id=200, text="Своё 10")

        async with _client() as c:
            csrf = await _login_as_user(c, db, 200, "Обычный")
            r = await c.post(
                "/costs/bulk-change-user",
                data={"ids": ["1"], "new_user_id": "100", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303
        # user_id should remain unchanged
        assert db.messages[1].user_id == 200

    @pytest.mark.asyncio
    async def test_admin_can_edit_any_cost(self, db, costs_patches):
        """Admin can edit any user's cost."""
        await db.save_message(None, user_id=200, text="Чужое 50")

        async with _client() as c:
            csrf = await _login(c)  # admin
            r = await c.post(
                "/costs/1/edit",
                data={
                    "name": "Обновлённое",
                    "amount": "75",
                    "user_id": "200",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
        assert r.status_code == 303

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_cost(self, db, costs_patches):
        """Admin can delete any user's cost."""
        await db.save_message(None, user_id=200, text="Чужое 50")

        async with _client() as c:
            csrf = await _login(c)  # admin
            r = await c.post(
                "/costs/1/delete",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert 1 not in db.messages

    @pytest.mark.asyncio
    async def test_admin_can_bulk_change_user(self, db, costs_patches):
        """Admin can bulk change user for any costs."""
        await db.save_message(None, user_id=200, text="Тест 50")

        async with _client() as c:
            csrf = await _login(c)  # admin
            r = await c.post(
                "/costs/bulk-change-user",
                data={"ids": ["1"], "new_user_id": "100", "csrf_token": csrf},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert db.messages[1].user_id == 100

    @pytest.mark.asyncio
    async def test_non_admin_list_hides_edit_delete_for_others(self, db, costs_patches):
        """Non-admin's costs list hides edit/delete buttons for other users' costs."""
        await db.save_message(None, user_id=200, text="Своё 10")
        await db.save_message(None, user_id=100, text="Чужое 20")

        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/costs")

        # Own cost should have edit button
        assert "/costs/1/edit" in r.text
        # Other user's cost should NOT have edit button
        assert "/costs/2/edit" not in r.text

    @pytest.mark.asyncio
    async def test_non_admin_list_hides_bulk_change_user(self, db, costs_patches):
        """Non-admin's costs list does not show bulk change user form."""
        await db.save_message(None, user_id=200, text="Своё 10")

        async with _client() as c:
            await _login_as_user(c, db, 200, "Обычный")
            r = await c.get("/costs")
        # The form action URL should not be present for non-admins
        assert "/costs/bulk-change-user" not in r.text
        assert "Изменить польз." not in r.text

    @pytest.mark.asyncio
    async def test_admin_list_shows_bulk_change_user(self, db, costs_patches):
        """Admin's costs list shows bulk change user form."""
        await db.save_message(None, user_id=100, text="Тест 10")

        async with _client() as c:
            await _login(c)  # admin
            r = await c.get("/costs")
        assert "/costs/bulk-change-user" in r.text
        assert "Изменить польз." in r.text

    @pytest.mark.asyncio
    async def test_login_stores_user_info_in_session(self, db):
        """Login correctly stores telegram_id, user_name, and role in session."""
        async with _client() as c:
            await _login(c, telegram_id=100)
            token = c.cookies[SESSION_COOKIE]
        session = auth_sessions[token]
        assert session["telegram_id"] == 100
        assert session["user_name"] == "Тестовый Админ"
        assert session["role"] == "admin"
