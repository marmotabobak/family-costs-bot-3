from unittest.mock import AsyncMock, patch
import pytest

from bot.db.dependencies import get_session


class TestGetSession:
    """Тесты контекстного менеджера сессии БД."""

    @pytest.mark.asyncio
    async def test_yields_session(self):
        """Возвращает сессию из session_maker."""
        mock_session = AsyncMock()

        with patch("bot.db.dependencies.async_session_maker", return_value=mock_session):
            async with get_session() as session:
                assert session is mock_session

    @pytest.mark.asyncio
    async def test_closes_session_on_success(self):
        """Закрывает сессию после успешного выполнения."""
        mock_session = AsyncMock()

        with patch("bot.db.dependencies.async_session_maker", return_value=mock_session):
            async with get_session():
                pass

        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_and_close_on_exception(self):
        """При исключении откатывает и закрывает сессию."""
        mock_session = AsyncMock()

        with patch("bot.db.dependencies.async_session_maker", return_value=mock_session):
            with pytest.raises(ValueError):
                async with get_session():
                    raise ValueError("test error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_reraises_exception(self):
        """Пробрасывает исключение после rollback."""
        mock_session = AsyncMock()

        with patch("bot.db.dependencies.async_session_maker", return_value=mock_session):
            with pytest.raises(ValueError, match="test error"):
                async with get_session():
                    raise ValueError("test error")
