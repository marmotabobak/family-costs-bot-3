"""Unit tests for costs management web UI."""

import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bot.web.costs import (
    SESSION_LIFETIME,
    CostsResponse,
    ParsedCost,
    auth_sessions,
    check_rate_limit,
    cleanup_expired_sessions,
    cleanup_old_rate_limits,
    generate_csrf_token,
    generate_session_token,
    get_csrf_token,
    get_flash_message,
    get_session_from_cookie,
    is_authenticated,
    login_attempts,
    parse_message_to_cost,
    record_login_attempt,
    set_flash_message,
    validate_csrf_token,
)


class TestParsedCostDataclass:
    """Tests for ParsedCost dataclass."""

    def test_creates_with_all_fields(self):
        """ParsedCost has all required fields."""
        now = datetime.now()
        cost = ParsedCost(
            id=1,
            name="Молоко",
            amount=Decimal("100.50"),
            user_id=123,
            created_at=now,
        )

        assert cost.id == 1
        assert cost.name == "Молоко"
        assert cost.amount == Decimal("100.50")
        assert cost.user_id == 123
        assert cost.created_at == now

    def test_handles_negative_amount(self):
        """ParsedCost accepts negative amounts."""
        cost = ParsedCost(
            id=1,
            name="Возврат",
            amount=Decimal("-50.00"),
            user_id=123,
            created_at=datetime.now(),
        )

        assert cost.amount == Decimal("-50.00")


class TestCostsResponseDataclass:
    """Tests for CostsResponse dataclass."""

    def test_creates_with_all_fields(self):
        """CostsResponse has all pagination fields."""
        response = CostsResponse(
            items=[],
            total=100,
            page=1,
            per_page=20,
            total_pages=5,
        )

        assert response.items == []
        assert response.total == 100
        assert response.page == 1
        assert response.per_page == 20
        assert response.total_pages == 5


class TestParseMessageToCost:
    """Tests for parse_message_to_cost function."""

    def test_parses_simple_message(self):
        """Parses simple 'name amount' format."""
        message = MagicMock()
        message.id = 1
        message.text = "Молоко 100"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Молоко"
        assert cost.amount == Decimal("100")

    def test_parses_multi_word_name(self):
        """Parses name with multiple words."""
        message = MagicMock()
        message.id = 1
        message.text = "Хлеб белый нарезной 50.50"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Хлеб белый нарезной"
        assert cost.amount == Decimal("50.50")

    def test_parses_comma_decimal(self):
        """Parses comma as decimal separator."""
        message = MagicMock()
        message.id = 1
        message.text = "Сыр 200,25"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.amount == Decimal("200.25")

    def test_parses_negative_amount(self):
        """Parses negative amounts."""
        message = MagicMock()
        message.id = 1
        message.text = "Возврат -50"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Возврат"
        assert cost.amount == Decimal("-50")

    def test_handles_invalid_amount(self):
        """Returns zero amount for invalid format."""
        message = MagicMock()
        message.id = 1
        message.text = "Невалидная строка"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Невалидная строка"
        assert cost.amount == Decimal("0")

    def test_handles_non_numeric_amount(self):
        """Returns zero for non-numeric amount."""
        message = MagicMock()
        message.id = 1
        message.text = "Молоко abc"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Молоко abc"
        assert cost.amount == Decimal("0")


class TestGenerateSessionToken:
    """Tests for generate_session_token function."""

    def test_generates_string(self):
        """Returns string token."""
        token = generate_session_token()
        assert isinstance(token, str)

    def test_generates_unique_tokens(self):
        """Each call generates unique token."""
        tokens = [generate_session_token() for _ in range(100)]
        assert len(set(tokens)) == 100

    def test_token_has_sufficient_length(self):
        """Token has at least 32 characters (256 bits of entropy)."""
        token = generate_session_token()
        assert len(token) >= 32


class TestGenerateCsrfToken:
    """Tests for generate_csrf_token function."""

    def test_generates_string(self):
        """Returns string token."""
        token = generate_csrf_token()
        assert isinstance(token, str)

    def test_generates_unique_tokens(self):
        """Each call generates unique token."""
        tokens = [generate_csrf_token() for _ in range(100)]
        assert len(set(tokens)) == 100


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions function."""

    def test_removes_expired_sessions(self):
        """Removes sessions older than SESSION_LIFETIME."""
        # Create expired session
        old_time = datetime.now() - timedelta(seconds=SESSION_LIFETIME + 100)
        token = "test-expired-token"
        auth_sessions[token] = {"authenticated": True, "created_at": old_time}

        cleanup_expired_sessions()

        assert token not in auth_sessions

    def test_keeps_valid_sessions(self):
        """Keeps sessions within lifetime."""
        token = "test-valid-token"
        auth_sessions[token] = {"authenticated": True, "created_at": datetime.now()}

        cleanup_expired_sessions()

        assert token in auth_sessions

        # Cleanup
        auth_sessions.pop(token, None)

    def test_handles_missing_created_at(self):
        """Handles sessions without created_at field."""
        token = "test-no-date-token"
        auth_sessions[token] = {"authenticated": True}

        # Should not raise
        cleanup_expired_sessions()

        # Session with no created_at is not expired (created_at defaults to now in check)
        assert token in auth_sessions

        # Cleanup
        auth_sessions.pop(token, None)


class TestGetSessionFromCookie:
    """Tests for get_session_from_cookie function."""

    def test_returns_none_for_no_cookie(self):
        """Returns None when no session cookie."""
        request = MagicMock()
        request.cookies.get.return_value = None

        session = get_session_from_cookie(request)

        assert session is None

    def test_returns_none_for_invalid_token(self):
        """Returns None for token not in sessions."""
        request = MagicMock()
        request.cookies.get.return_value = "invalid-token"

        session = get_session_from_cookie(request)

        assert session is None

    def test_returns_session_for_valid_token(self):
        """Returns session data for valid token."""
        token = "valid-session-token"
        session_data = {"authenticated": True, "created_at": datetime.now()}
        auth_sessions[token] = session_data

        request = MagicMock()
        request.cookies.get.return_value = token

        session = get_session_from_cookie(request)

        assert session == session_data

        # Cleanup
        auth_sessions.pop(token, None)

    def test_returns_none_for_expired_session(self):
        """Returns None and cleans up expired session."""
        token = "expired-session-token"
        old_time = datetime.now() - timedelta(seconds=SESSION_LIFETIME + 100)
        auth_sessions[token] = {"authenticated": True, "created_at": old_time}

        request = MagicMock()
        request.cookies.get.return_value = token

        session = get_session_from_cookie(request)

        assert session is None
        assert token not in auth_sessions


class TestIsAuthenticated:
    """Tests for is_authenticated function."""

    def test_returns_false_for_no_session(self):
        """Returns False when no session."""
        request = MagicMock()
        request.cookies.get.return_value = None

        assert is_authenticated(request) is False

    def test_returns_false_for_unauthenticated_session(self):
        """Returns False when session exists but not authenticated."""
        token = "unauth-session"
        auth_sessions[token] = {"authenticated": False, "created_at": datetime.now()}

        request = MagicMock()
        request.cookies.get.return_value = token

        assert is_authenticated(request) is False

        # Cleanup
        auth_sessions.pop(token, None)

    def test_returns_true_for_authenticated_session(self):
        """Returns True for authenticated session."""
        token = "auth-session"
        auth_sessions[token] = {"authenticated": True, "created_at": datetime.now()}

        request = MagicMock()
        request.cookies.get.return_value = token

        assert is_authenticated(request) is True

        # Cleanup
        auth_sessions.pop(token, None)


class TestGetCsrfToken:
    """Tests for get_csrf_token function."""

    def test_returns_none_for_no_session(self):
        """Returns None when no session."""
        request = MagicMock()
        request.cookies.get.return_value = None

        assert get_csrf_token(request) is None

    def test_returns_csrf_from_session(self):
        """Returns CSRF token from session."""
        token = "csrf-test-session"
        csrf = "test-csrf-token"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": csrf,
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        assert get_csrf_token(request) == csrf

        # Cleanup
        auth_sessions.pop(token, None)


class TestValidateCsrfToken:
    """Tests for validate_csrf_token function."""

    def test_returns_false_for_no_session(self):
        """Returns False when no session."""
        request = MagicMock()
        request.cookies.get.return_value = None

        assert validate_csrf_token(request, "some-token") is False

    def test_returns_false_for_wrong_token(self):
        """Returns False for incorrect token."""
        session_token = "validate-csrf-session"
        csrf = "correct-csrf"
        auth_sessions[session_token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": csrf,
        }

        request = MagicMock()
        request.cookies.get.return_value = session_token

        assert validate_csrf_token(request, "wrong-csrf") is False

        # Cleanup
        auth_sessions.pop(session_token, None)

    def test_returns_true_for_correct_token(self):
        """Returns True for correct token."""
        session_token = "validate-csrf-session-2"
        csrf = "correct-csrf-token"
        auth_sessions[session_token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": csrf,
        }

        request = MagicMock()
        request.cookies.get.return_value = session_token

        assert validate_csrf_token(request, csrf) is True

        # Cleanup
        auth_sessions.pop(session_token, None)

    def test_uses_timing_safe_comparison(self):
        """Uses secrets.compare_digest for timing-safe comparison."""
        session_token = "timing-safe-session"
        csrf = "timing-safe-csrf"
        auth_sessions[session_token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": csrf,
        }

        request = MagicMock()
        request.cookies.get.return_value = session_token

        with patch("bot.web.costs.secrets.compare_digest") as mock_compare:
            mock_compare.return_value = True
            validate_csrf_token(request, csrf)
            mock_compare.assert_called_once_with(csrf, csrf)

        # Cleanup
        auth_sessions.pop(session_token, None)


class TestCheckRateLimit:
    """Tests for check_rate_limit function."""

    def test_allows_first_attempt(self):
        """Allows first login attempt."""
        ip = "192.168.1.100"
        login_attempts.pop(ip, None)

        assert check_rate_limit(ip) is True

        # Cleanup
        login_attempts.pop(ip, None)

    def test_allows_up_to_max_attempts(self):
        """Allows up to MAX_LOGIN_ATTEMPTS."""
        ip = "192.168.1.101"
        login_attempts.pop(ip, None)

        for _ in range(5):
            assert check_rate_limit(ip) is True
            record_login_attempt(ip)

        # 6th attempt should be blocked
        assert check_rate_limit(ip) is False

        # Cleanup
        login_attempts.pop(ip, None)

    def test_cleans_old_attempts(self):
        """Removes attempts outside time window."""
        ip = "192.168.1.102"
        # Add old attempt (more than 5 minutes ago)
        login_attempts[ip] = [time.time() - 400]

        # Should still be allowed (old attempt cleaned)
        assert check_rate_limit(ip) is True

        # Cleanup
        login_attempts.pop(ip, None)


class TestRecordLoginAttempt:
    """Tests for record_login_attempt function."""

    def test_records_attempt(self):
        """Records login attempt timestamp."""
        ip = "192.168.1.103"
        login_attempts.pop(ip, None)

        before = time.time()
        record_login_attempt(ip)
        after = time.time()

        assert len(login_attempts[ip]) == 1
        assert before <= login_attempts[ip][0] <= after

        # Cleanup
        login_attempts.pop(ip, None)


class TestCleanupOldRateLimits:
    """Tests for cleanup_old_rate_limits function."""

    def test_removes_stale_ips(self):
        """Removes IPs with only old attempts."""
        ip = "192.168.1.104"
        login_attempts[ip] = [time.time() - 400]

        cleanup_old_rate_limits()

        assert ip not in login_attempts

    def test_keeps_recent_ips(self):
        """Keeps IPs with recent attempts."""
        ip = "192.168.1.105"
        login_attempts[ip] = [time.time()]

        cleanup_old_rate_limits()

        assert ip in login_attempts

        # Cleanup
        login_attempts.pop(ip, None)

    def test_removes_empty_entries(self):
        """Removes IPs with empty attempt lists."""
        ip = "192.168.1.106"
        login_attempts[ip] = []

        cleanup_old_rate_limits()

        assert ip not in login_attempts


class TestGetFlashMessage:
    """Tests for get_flash_message function."""

    def test_returns_none_for_no_session(self):
        """Returns None when no session."""
        request = MagicMock()
        request.cookies.get.return_value = None

        message, msg_type = get_flash_message(request)

        assert message is None
        assert msg_type is None

    def test_returns_message_and_clears(self):
        """Returns flash message and clears it from session."""
        token = "flash-test-session"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "flash_message": "Успех!",
            "flash_type": "success",
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        message, msg_type = get_flash_message(request)

        assert message == "Успех!"
        assert msg_type == "success"
        assert "flash_message" not in auth_sessions[token]
        assert "flash_type" not in auth_sessions[token]

        # Cleanup
        auth_sessions.pop(token, None)

    def test_returns_default_type_when_missing(self):
        """Returns 'info' as default type when flash_type missing."""
        token = "flash-default-type"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "flash_message": "Сообщение",
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        message, msg_type = get_flash_message(request)

        assert message == "Сообщение"
        assert msg_type == "info"

        # Cleanup
        auth_sessions.pop(token, None)


class TestSetFlashMessage:
    """Tests for set_flash_message function."""

    def test_does_nothing_for_no_session(self):
        """Does nothing when no session."""
        request = MagicMock()
        request.cookies.get.return_value = None

        # Should not raise
        set_flash_message(request, "Test message")

    def test_sets_message_and_type(self):
        """Sets flash message and type in session."""
        token = "set-flash-session"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        set_flash_message(request, "Ошибка!", "error")

        assert auth_sessions[token]["flash_message"] == "Ошибка!"
        assert auth_sessions[token]["flash_type"] == "error"

        # Cleanup
        auth_sessions.pop(token, None)

    def test_default_type_is_info(self):
        """Default flash type is 'info'."""
        token = "set-flash-default"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        set_flash_message(request, "Инфо")

        assert auth_sessions[token]["flash_type"] == "info"

        # Cleanup
        auth_sessions.pop(token, None)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_parse_empty_text(self):
        """Handles empty text message."""
        message = MagicMock()
        message.id = 1
        message.text = ""
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == ""
        assert cost.amount == Decimal("0")

    def test_parse_whitespace_only(self):
        """Handles whitespace-only text."""
        message = MagicMock()
        message.id = 1
        message.text = "   "
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.amount == Decimal("0")

    def test_parse_very_large_amount(self):
        """Handles very large amount."""
        message = MagicMock()
        message.id = 1
        message.text = "Большая покупка 999999999.99"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.amount == Decimal("999999999.99")

    def test_parse_very_small_amount(self):
        """Handles very small decimal amount."""
        message = MagicMock()
        message.id = 1
        message.text = "Копейка 0.01"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.amount == Decimal("0.01")

    def test_parse_unicode_name(self):
        """Handles unicode characters in name."""
        message = MagicMock()
        message.id = 1
        message.text = "Кафе ☕ завтрак 350"
        message.user_id = 123
        message.created_at = datetime.now()

        cost = parse_message_to_cost(message)

        assert cost.name == "Кафе ☕ завтрак"
        assert cost.amount == Decimal("350")

    def test_validate_csrf_empty_token(self):
        """Returns False for empty CSRF token."""
        token = "csrf-empty-test"
        auth_sessions[token] = {
            "authenticated": True,
            "created_at": datetime.now(),
            "csrf_token": "valid-csrf",
        }

        request = MagicMock()
        request.cookies.get.return_value = token

        # Empty string token
        assert validate_csrf_token(request, "") is False

        # Cleanup
        auth_sessions.pop(token, None)
