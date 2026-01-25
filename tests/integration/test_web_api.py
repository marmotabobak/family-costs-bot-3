"""Integration tests for Web API endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bot.web.app import app, generate_import_token, import_sessions


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Generate valid import token."""
    token = generate_import_token(user_id=999999)
    yield token
    # Cleanup
    import_sessions.pop(token, None)


@pytest.fixture
def mock_db_session():
    """Mock database session for testing save functionality."""
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


@pytest.fixture
def sample_vkusvill_json():
    """Sample VkusVill export JSON."""
    return {
        "exportDate": "2026-01-24",
        "checks": [
            {
                "id": "12345",
                "uid": "TEST-UID-1",
                "date": "2026-01-24T13:24",
                "store": "Test Store",
                "total": 250,
                "items": [
                    {"name": "Product 1", "quantity": 1, "price": 100, "sum": 100},
                    {"name": "Product 2", "quantity": 2, "price": 75, "sum": 150},
                ],
            },
            {
                "id": "12346",
                "uid": "TEST-UID-2",
                "date": "2026-01-25T10:00",
                "store": "Test Store 2",
                "total": 50,
                "items": [
                    {"name": "Product 3", "quantity": 1, "price": 50, "sum": 50},
                ],
            },
        ],
    }


class TestHealthEndpoint:
    """Integration tests for /health endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint returns 200 OK."""
        response = client.get("/health")

        assert response.status_code == 200

    def test_health_returns_status_ok(self, client):
        """Health endpoint returns status ok JSON."""
        response = client.get("/health")

        assert response.json() == {"status": "ok"}


class TestDevTokenEndpoint:
    """Integration tests for /dev/create-token endpoint."""

    def test_creates_token_for_user(self, client):
        """Dev endpoint creates valid token."""
        response = client.get("/dev/create-token/12345")

        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "url" in data
        assert data["url"].startswith("/import/")

        # Cleanup
        import_sessions.pop(data["token"], None)

    def test_token_is_valid_for_import(self, client):
        """Created token can be used for import."""
        # Create token
        response = client.get("/dev/create-token/12345")
        token = response.json()["token"]

        # Use token
        response = client.get(f"/import/{token}")
        assert response.status_code == 200

        # Cleanup
        import_sessions.pop(token, None)


class TestFullImportFlow:
    """Integration tests for full import flow."""

    def test_upload_page_accessible(self, client, valid_token):
        """Upload page is accessible with valid token."""
        response = client.get(f"/import/{valid_token}")

        assert response.status_code == 200
        assert "upload" in response.text.lower() or "загрузить" in response.text.lower()

    def test_upload_page_404_invalid_token(self, client):
        """Upload page returns 404 for invalid token."""
        response = client.get("/import/invalid-token-12345")

        assert response.status_code == 404

    def test_upload_json_file(self, client, valid_token, sample_vkusvill_json):
        """Upload JSON file stores data in session."""
        json_content = json.dumps(sample_vkusvill_json)

        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Should redirect to select page
        assert response.status_code == 303
        assert f"/import/{valid_token}/select" in response.headers["location"]

        # Data should be in session
        session = import_sessions.get(valid_token)
        assert session is not None
        assert session["data"] is not None
        assert len(session["data"]["checks"]) == 2

    def test_select_page_shows_items(self, client, valid_token, sample_vkusvill_json):
        """Select page displays all items from uploaded checks."""
        # Upload first
        json_content = json.dumps(sample_vkusvill_json)
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Access select page
        response = client.get(f"/import/{valid_token}/select")

        assert response.status_code == 200
        assert "Product 1" in response.text
        assert "Product 2" in response.text
        assert "Product 3" in response.text

    def test_save_selected_items(self, client, valid_token, sample_vkusvill_json, mock_db_session):
        """Save endpoint processes selected items."""
        # Upload first
        json_content = json.dumps(sample_vkusvill_json)
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        with patch("bot.web.app.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Select and save items (check 0, items 0 and 1)
            response = client.post(
                f"/import/{valid_token}/save",
                data={"items": ["0:0", "0:1"]},
            )

        assert response.status_code == 200
        assert "2" in response.text  # saved count
        assert "250" in response.text  # total amount (100 + 150)

    def test_save_clears_session_data(self, client, valid_token, sample_vkusvill_json, mock_db_session):
        """Save endpoint clears session data after saving."""
        # Upload
        json_content = json.dumps(sample_vkusvill_json)
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        with patch("bot.web.app.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Save
            client.post(
                f"/import/{valid_token}/save",
                data={"items": ["0:0"]},
            )

        # Session data should be cleared
        session = import_sessions.get(valid_token)
        assert session["data"] is None

    def test_save_no_items_shows_error(self, client, valid_token, sample_vkusvill_json):
        """Save without selected items shows error."""
        # Upload
        json_content = json.dumps(sample_vkusvill_json)
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Try to save without selecting
        response = client.post(
            f"/import/{valid_token}/save",
            data={},
        )

        assert response.status_code == 200
        assert "выберите" in response.text.lower() or "error" in response.text.lower()


class TestUploadValidation:
    """Tests for upload validation."""

    def test_upload_invalid_json(self, client, valid_token):
        """Upload rejects invalid JSON."""
        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", "not valid json", "application/json")},
        )

        assert response.status_code == 200
        assert "ошибка" in response.text.lower() or "error" in response.text.lower()

    def test_upload_json_without_checks(self, client, valid_token):
        """Upload rejects JSON without checks field."""
        json_content = json.dumps({"someField": "value"})

        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("data.json", json_content, "application/json")},
        )

        assert response.status_code == 200
        assert "формат" in response.text.lower() or "error" in response.text.lower()

    def test_upload_empty_checks(self, client, valid_token):
        """Upload handles empty checks array."""
        json_content = json.dumps({"checks": []})

        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("data.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Should still redirect (empty is valid structure)
        assert response.status_code == 303


class TestSessionIsolation:
    """Tests for session isolation between users."""

    def test_different_tokens_isolated(self, client):
        """Different tokens have isolated sessions."""
        # Create two tokens
        resp1 = client.get("/dev/create-token/111")
        resp2 = client.get("/dev/create-token/222")

        token1 = resp1.json()["token"]
        token2 = resp2.json()["token"]

        # Upload to token1
        json_content = json.dumps(
            {"checks": [{"id": "1", "uid": "U1", "date": "2026-01-01T10:00", "store": "S", "total": 100, "items": []}]}
        )
        client.post(
            f"/import/{token1}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Token2 should not have data
        session2 = import_sessions.get(token2)
        assert session2["data"] is None

        # Cleanup
        import_sessions.pop(token1, None)
        import_sessions.pop(token2, None)

    def test_cannot_access_other_token(self, client, valid_token):
        """Cannot access another user's token."""
        # Upload data to valid_token
        json_content = json.dumps(
            {"checks": [{"id": "1", "uid": "U1", "date": "2026-01-01T10:00", "store": "S", "total": 100, "items": []}]}
        )
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Try to access with different (invalid) token
        response = client.get("/import/some-other-token/select")
        assert response.status_code == 404
