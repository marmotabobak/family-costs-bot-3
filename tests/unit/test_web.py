"""Tests for web UI (VkusVill import)."""

import json

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
    token = generate_import_token(user_id=123456)
    yield token
    # Cleanup
    import_sessions.pop(token, None)


@pytest.fixture
def sample_json():
    """Sample VkusVill export JSON."""
    return {
        "exportDate": "2026-01-24",
        "checks": [
            {
                "id": "12795",
                "uid": "5FC0B203-0FF9-F011-9070-005056A7A8DF",
                "date": "2026-01-24T13:24",
                "store": "Москва б-р Осенний, д. 9",
                "total": 335,
                "items": [
                    {
                        "name": "Напиток на пихтовой воде",
                        "quantity": 1,
                        "price": 109,
                        "sum": 109,
                    },
                    {
                        "name": "Вафли Голландские",
                        "quantity": 1,
                        "price": 153,
                        "sum": 153,
                    },
                ],
            },
            {
                "id": "98318",
                "uid": "E337B32B-7C99-440C-A305-9D4DCC03EFFB",
                "date": "2026-01-23T10:54",
                "store": "Москва Рублёвское ш.",
                "total": 238,
                "items": [
                    {
                        "name": "Молоко 2,5%",
                        "quantity": 1,
                        "price": 142,
                        "sum": 142,
                    },
                    {
                        "name": "Молоко 1%",
                        "quantity": 1,
                        "price": 96,
                        "sum": 96,
                    },
                ],
            },
        ],
    }


class TestGenerateImportToken:
    """Tests for token generation."""

    def test_generates_unique_tokens(self):
        """Each call generates unique token."""
        token1 = generate_import_token(user_id=123)
        token2 = generate_import_token(user_id=123)

        assert token1 != token2

        # Cleanup
        import_sessions.pop(token1, None)
        import_sessions.pop(token2, None)

    def test_stores_user_id_in_session(self):
        """Token session contains user_id."""
        token = generate_import_token(user_id=999)

        assert token in import_sessions
        assert import_sessions[token]["user_id"] == 999

        # Cleanup
        import_sessions.pop(token, None)

    def test_session_has_created_at(self):
        """Token session has creation timestamp."""
        token = generate_import_token(user_id=123)

        assert "created_at" in import_sessions[token]
        assert import_sessions[token]["created_at"] is not None

        # Cleanup
        import_sessions.pop(token, None)


class TestUploadPage:
    """Tests for upload page."""

    def test_returns_200_with_valid_token(self, client, valid_token):
        """Upload page accessible with valid token."""
        response = client.get(f"/import/{valid_token}")

        assert response.status_code == 200
        assert "Загрузите файл" in response.text

    def test_returns_404_with_invalid_token(self, client):
        """Upload page returns 404 for invalid token."""
        response = client.get("/import/invalid-token-123")

        assert response.status_code == 404

    def test_contains_upload_form(self, client, valid_token):
        """Page contains file upload form."""
        response = client.get(f"/import/{valid_token}")

        assert 'type="file"' in response.text
        assert 'accept=".json"' in response.text


class TestFileUpload:
    """Tests for JSON file upload."""

    def test_upload_valid_json(self, client, valid_token, sample_json):
        """Uploading valid JSON redirects to select page."""
        json_content = json.dumps(sample_json).encode()

        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert f"/import/{valid_token}/select" in response.headers["location"]

    def test_upload_invalid_json(self, client, valid_token):
        """Uploading invalid JSON shows error."""
        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", b"not json", "application/json")},
        )

        assert response.status_code == 200
        assert "Ошибка чтения файла" in response.text

    def test_upload_json_without_checks(self, client, valid_token):
        """Uploading JSON without 'checks' key shows error."""
        json_content = json.dumps({"data": []}).encode()

        response = client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
        )

        assert response.status_code == 200
        assert "Неверный формат файла" in response.text

    def test_upload_stores_data_in_session(self, client, valid_token, sample_json):
        """Uploaded data is stored in session."""
        json_content = json.dumps(sample_json).encode()

        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        assert import_sessions[valid_token]["data"] == sample_json


class TestSelectPage:
    """Tests for check/item selection page."""

    def test_returns_200_with_data(self, client, valid_token, sample_json):
        """Select page accessible when data is uploaded."""
        # First upload
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Then access select page
        response = client.get(f"/import/{valid_token}/select")

        assert response.status_code == 200
        assert "Выберите товары" in response.text

    def test_redirects_without_data(self, client, valid_token):
        """Select page redirects to upload if no data."""
        response = client.get(f"/import/{valid_token}/select", follow_redirects=False)

        assert response.status_code == 307

    def test_shows_all_checks(self, client, valid_token, sample_json):
        """Select page displays all checks."""
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        response = client.get(f"/import/{valid_token}/select")

        assert "Москва б-р Осенний" in response.text
        assert "Москва Рублёвское" in response.text
        assert "335" in response.text
        assert "238" in response.text

    def test_shows_all_items(self, client, valid_token, sample_json):
        """Select page displays all items."""
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        response = client.get(f"/import/{valid_token}/select")

        assert "Напиток на пихтовой воде" in response.text
        assert "Вафли Голландские" in response.text
        assert "Молоко 2,5%" in response.text


class TestSaveSelected:
    """Tests for saving selected items."""

    def test_save_selected_items(self, client, valid_token, sample_json):
        """Saving selected items shows success page."""
        # Upload
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Save selected items (first item from first check, second from second)
        response = client.post(
            f"/import/{valid_token}/save",
            data={"items": ["0:0", "1:1"]},
        )

        assert response.status_code == 200
        assert "Данные сохранены" in response.text
        assert "2" in response.text  # 2 items saved

    def test_save_no_items_shows_error(self, client, valid_token, sample_json):
        """Saving with no selection shows error."""
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        response = client.post(
            f"/import/{valid_token}/save",
            data={},
        )

        assert response.status_code == 200
        assert "Выберите хотя бы один товар" in response.text

    def test_save_clears_session_data(self, client, valid_token, sample_json):
        """After save, session data is cleared."""
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        client.post(
            f"/import/{valid_token}/save",
            data={"items": ["0:0"]},
        )

        assert import_sessions[valid_token]["data"] is None

    def test_save_calculates_total(self, client, valid_token, sample_json):
        """Success page shows correct total amount."""
        json_content = json.dumps(sample_json).encode()
        client.post(
            f"/import/{valid_token}/upload",
            files={"file": ("checks.json", json_content, "application/json")},
            follow_redirects=False,
        )

        # Select items with sum 109 + 96 = 205
        response = client.post(
            f"/import/{valid_token}/save",
            data={"items": ["0:0", "1:1"]},
        )

        assert "205" in response.text
