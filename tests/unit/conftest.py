from unittest.mock import AsyncMock, MagicMock
import pytest


@pytest.fixture
def mock_message():
    """Создаёт мок aiogram Message."""
    message = AsyncMock()
    message.text = "Продукты 100"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_session():
    """Создаёт мок асинхронной сессии БД."""
    session = AsyncMock()
    session.add = MagicMock()
    return session
