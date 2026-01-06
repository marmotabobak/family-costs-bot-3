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


@pytest.fixture
def mock_state():
    """Создаёт мок FSMContext."""
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state
