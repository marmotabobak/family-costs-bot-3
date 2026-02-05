"""Тесты для роутера меню."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.routers.menu import (
    CALLBACK_MONTH_PREFIX,
    CALLBACK_MY_COSTS,
    CALLBACK_PERIOD_PREFIX,
    CALLBACK_SUMMARY,
    CALLBACK_SUMMARY_MONTH_PREFIX,
    CALLBACK_SUMMARY_PERIOD_PREFIX,
    CALLBACK_USER_COSTS_PREFIX,
    build_menu_keyboard,
    build_months_keyboard,
    build_period_keyboard,
    build_summary_months_keyboard,
    build_summary_period_keyboard,
    format_month_report,
    format_summary_report,
    handle_month_selection,
    handle_my_costs,
    handle_period_selection,
    handle_summary,
    handle_summary_month_selection,
    handle_summary_period_selection,
    handle_user_costs,
    menu_command,
)


class TestBuildMenuKeyboard:
    """Тесты построения главного меню."""

    def test_empty_user_list(self):
        """Пустой список пользователей - кнопка 'Мои расходы' и 'Сводная'."""
        keyboard = build_menu_keyboard(current_user_id=123, user_names={})

        assert len(keyboard.inline_keyboard) == 2
        assert keyboard.inline_keyboard[0][0].text == "📊 Мои расходы"
        assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_MY_COSTS
        assert keyboard.inline_keyboard[1][0].text == "📈 Сводная"
        assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_SUMMARY

    def test_current_user_excluded(self):
        """Текущий пользователь не показывается в списке."""
        keyboard = build_menu_keyboard(current_user_id=123, user_names={123: "Alice", 456: "Bob", 789: "Carol"})

        # 1 (Мои расходы) + 2 (другие пользователи) + 1 (Сводная) = 4
        assert len(keyboard.inline_keyboard) == 4

        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" not in callback_datas

    def test_all_users_shown(self):
        """Все пользователи кроме текущего показаны."""
        keyboard = build_menu_keyboard(current_user_id=100, user_names={123: "Alice", 456: "Bob", 789: "Carol"})

        # 1 (Мои расходы) + 3 (пользователи) + 1 (Сводная) = 5
        assert len(keyboard.inline_keyboard) == 5

        # Пользователи в средних кнопках (индексы 1-3)
        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard[1:-1]]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}456" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}789" in callback_datas

    def test_summary_button_last(self):
        """Кнопка 'Сводная' всегда последняя."""
        keyboard = build_menu_keyboard(current_user_id=100, user_names={123: "Alice"})

        last_button = keyboard.inline_keyboard[-1][0]
        assert last_button.text == "📈 Сводная"
        assert last_button.callback_data == CALLBACK_SUMMARY


class TestBuildPeriodKeyboard:
    """Тесты построения меню выбора периода."""

    def test_has_three_buttons(self):
        """Клавиатура содержит 3 кнопки (3 периода)."""
        keyboard = build_period_keyboard(user_id=123)

        assert len(keyboard.inline_keyboard) == 3

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        keyboard = build_period_keyboard(user_id=456)

        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert f"{CALLBACK_PERIOD_PREFIX}456:this_month" in callback_datas
        assert f"{CALLBACK_PERIOD_PREFIX}456:prev_month" in callback_datas
        assert f"{CALLBACK_PERIOD_PREFIX}456:other" in callback_datas


class TestBuildMonthsKeyboard:
    """Тесты построения меню выбора месяца."""

    def test_creates_buttons_for_months(self):
        """Создаёт кнопки для каждого месяца."""
        months = [(2024, 1), (2024, 2), (2023, 12)]
        keyboard = build_months_keyboard(user_id=123, available_months=months)

        assert len(keyboard.inline_keyboard) == 3

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        months = [(2024, 3)]
        keyboard = build_months_keyboard(user_id=456, available_months=months)

        assert keyboard.inline_keyboard[0][0].callback_data == f"{CALLBACK_MONTH_PREFIX}456:2024:3"

    def test_button_text_contains_month_name(self):
        """Текст кнопки содержит название месяца."""
        months = [(2024, 1)]
        keyboard = build_months_keyboard(user_id=123, available_months=months)

        assert "Январь" in keyboard.inline_keyboard[0][0].text
        assert "2024" in keyboard.inline_keyboard[0][0].text


class TestFormatMonthReport:
    """Тесты форматирования отчёта за месяц."""

    def test_empty_costs_own(self):
        """Пустой отчёт для своих расходов."""
        report = format_month_report([], year=2024, month=1, user_name="", is_own=True)

        assert "Январь 2024" in report
        assert "Нет расходов" in report

    def test_empty_costs_other_user(self):
        """Пустой отчёт для чужих расходов."""
        report = format_month_report([], year=2024, month=1, user_name="456", is_own=False)

        assert "Январь 2024" in report
        assert "456" in report

    def test_report_with_costs(self):
        """Отчёт с расходами."""
        costs = [
            ("Продукты", Decimal("100.00"), datetime(2024, 1, 15, 10, 0)),
            ("Транспорт", Decimal("50.50"), datetime(2024, 1, 20, 12, 30)),
            ("\\-.!#_@:`<>/", Decimal("12.34"), datetime(2024, 1, 2, 3, 4)),
        ]
        report = format_month_report(costs, year=2024, month=1, user_name="", is_own=True)

        assert "<b>Январь 2024</b>" in report
        assert "<b>Всего:</b> 162.84" in report  # total (has fractional)
        assert "15: Продукты 100" in report  # 100.00 → no .00
        assert "20: Транспорт 50.50" in report
        assert "2: \\-.!#_@:`<>/ 12.34" in report


class TestMenuCommand:
    """Тесты команды /menu."""

    @pytest.fixture
    def message(self):
        """Фикстура сообщения."""
        from aiogram.types import Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.answer = AsyncMock()

        return msg

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.from_user = None
        msg.answer = AsyncMock()

        await menu_command(msg)

        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_menu_with_keyboard(self, message):
        """Отправляет меню с клавиатурой."""
        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_unique_user_ids") as mock_get_users,
            patch("bot.routers.menu.get_all_users") as mock_get_all_users,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_users.return_value = [123, 456]
            mock_get_all_users.return_value = []

            await menu_command(message)

            message.answer.assert_called_once()
            call_kwargs = message.answer.call_args.kwargs
            assert "reply_markup" in call_kwargs


class TestHandleMyCosts:
    """Тесты обработчика 'Мои расходы'."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_MY_COSTS
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.answer = AsyncMock()

        await handle_my_costs(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_period_selection(self, callback):
        """Показывает выбор периода."""
        await handle_my_costs(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        call_kwargs = callback.message.answer.call_args.kwargs
        assert "reply_markup" in call_kwargs


class TestHandleUserCosts:
    """Тесты обработчика 'Расходы <user_id>'."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = f"{CALLBACK_USER_COSTS_PREFIX}456"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.data = None
        cb.answer = AsyncMock()

        await handle_user_costs(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_period_selection_for_target_user(self, callback):
        """Показывает выбор периода для целевого пользователя."""
        await handle_user_costs(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        response = callback.message.answer.call_args[0][0]
        assert "456" in response

    @pytest.mark.asyncio
    async def test_invalid_user_id_shows_error(self, callback):
        """Некорректный user_id показывает ошибку."""
        callback.data = f"{CALLBACK_USER_COSTS_PREFIX}not_a_number"

        await handle_user_costs(callback)

        callback.answer.assert_called_once_with("Ошибка: некорректный ID пользователя")
        callback.message.answer.assert_not_called()


class TestHandlePeriodSelection:
    """Тесты обработчика выбора периода."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_this_month_shows_report(self, callback):
        """Выбор 'Этот месяц' показывает отчёт."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}123:this_month"

        mock_session = AsyncMock()
        mock_costs = [("Продукты", Decimal("100.00"), datetime.now())]

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_user_costs_by_month") as mock_get_costs,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = mock_costs

            await handle_period_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_other_shows_months_list(self, callback):
        """Выбор 'Другие месяцы' показывает список месяцев."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}123:other"

        mock_session = AsyncMock()
        mock_months = [(2024, 1), (2024, 2)]

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.db.repositories.messages.get_user_available_months") as mock_get_months,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_months.return_value = mock_months

            await handle_period_selection(callback)

            callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_early_without_data(self):
        """Выходит если callback.data пустой."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = None
        cb.answer = AsyncMock()

        await handle_period_selection(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_returns_error(self, callback):
        """Неверный формат callback_data показывает ошибку."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}invalid_format"

        await handle_period_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_error(self, callback):
        """Некорректный user_id показывает ошибку."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}not_a_number:this_month"

        await handle_period_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_prev_month_shows_report(self, callback):
        """Выбор 'Прошлый месяц' показывает отчёт."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}123:prev_month"

        mock_session = AsyncMock()
        mock_costs = [("Продукты", Decimal("100.00"), datetime.now())]

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_user_costs_by_month") as mock_get_costs,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = mock_costs

            await handle_period_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_prev_month_january_goes_to_december(self, callback):
        """В январе 'Прошлый месяц' показывает декабрь прошлого года."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}123:prev_month"

        mock_session = AsyncMock()
        mock_costs: list[tuple] = []

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_user_costs_by_month") as mock_get_costs,
            patch("bot.routers.menu.datetime") as mock_datetime,
        ):
            mock_now = MagicMock()
            mock_now.year = 2026
            mock_now.month = 1  # January
            mock_datetime.now.return_value = mock_now

            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = mock_costs

            await handle_period_selection(callback)

            # Проверяем что вызван с декабрём 2025
            mock_get_costs.assert_called_once()
            call_args = mock_get_costs.call_args
            assert call_args[0][2] == 2025  # year
            assert call_args[0][3] == 12  # month

    @pytest.mark.asyncio
    async def test_unknown_period_returns_error(self, callback):
        """Неизвестный тип периода показывает ошибку."""
        callback.data = f"{CALLBACK_PERIOD_PREFIX}123:unknown_period"

        await handle_period_selection(callback)

        callback.answer.assert_called_once_with("Неизвестный период")


class TestHandleMonthSelection:
    """Тесты обработчика выбора конкретного месяца."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = f"{CALLBACK_MONTH_PREFIX}123:2024:1"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_shows_month_report(self, callback):
        """Показывает отчёт за выбранный месяц."""
        mock_session = AsyncMock()
        mock_costs = [("Продукты", Decimal("100.00"), datetime(2024, 1, 15))]

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_user_costs_by_month") as mock_get_costs,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = mock_costs

            await handle_month_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

            response = callback.message.answer.call_args[0][0]
            assert "Январь 2024" in response

    @pytest.mark.asyncio
    async def test_returns_early_without_data(self):
        """Выходит если callback.data пустой."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = None
        cb.answer = AsyncMock()

        await handle_month_selection(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_returns_error(self, callback):
        """Неверный формат callback_data показывает ошибку."""
        callback.data = f"{CALLBACK_MONTH_PREFIX}invalid"

        await handle_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_error(self, callback):
        """Некорректный user_id показывает ошибку."""
        callback.data = f"{CALLBACK_MONTH_PREFIX}not_a_number:2024:1"

        await handle_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_year_returns_error(self, callback):
        """Некорректный год показывает ошибку."""
        callback.data = f"{CALLBACK_MONTH_PREFIX}123:not_a_year:1"

        await handle_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_month_returns_error(self, callback):
        """Некорректный месяц показывает ошибку."""
        callback.data = f"{CALLBACK_MONTH_PREFIX}123:2024:not_a_month"

        await handle_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")


class TestShowMonthsList:
    """Тесты для _show_months_list."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_empty_months_shows_message(self, callback):
        """Пустой список месяцев показывает сообщение."""
        from bot.routers.menu import _show_months_list

        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.db.repositories.messages.get_user_available_months") as mock_get_months,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_months.return_value = []

            await _show_months_list(callback, user_id=123, is_own=True)

            callback.answer.assert_called_once()
            response = callback.message.answer.call_args[0][0]
            assert "Нет данных" in response

    @pytest.mark.asyncio
    async def test_empty_months_other_user_shows_user_id(self, callback):
        """Пустой список месяцев для чужого пользователя показывает его ID."""
        from bot.routers.menu import _show_months_list

        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.db.repositories.messages.get_user_available_months") as mock_get_months,
            patch("bot.routers.menu.get_user_by_telegram_id", new=AsyncMock(return_value=None)),
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_months.return_value = []

            await _show_months_list(callback, user_id=456, is_own=False)

            response = callback.message.answer.call_args[0][0]
            assert "456" in response


class TestShowMonthReport:
    """Тесты для _show_month_report."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_message(self):
        """Выходит если message не является Message."""
        from aiogram.types import CallbackQuery
        from bot.routers.menu import _show_month_report

        cb = MagicMock(spec=CallbackQuery)
        cb.message = None  # Не Message

        await _show_month_report(cb, user_id=123, year=2024, month=1, is_own=True)

        # Не должен вызывать ничего
        # Просто проверяем что не падает


# --- Тесты сводного отчёта ---


class TestBuildSummaryPeriodKeyboard:
    """Тесты построения меню выбора периода для сводного отчёта."""

    def test_has_three_buttons(self):
        """Клавиатура содержит 3 кнопки (3 периода)."""
        keyboard = build_summary_period_keyboard()

        assert len(keyboard.inline_keyboard) == 3

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        keyboard = build_summary_period_keyboard()

        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert f"{CALLBACK_SUMMARY_PERIOD_PREFIX}this_month" in callback_datas
        assert f"{CALLBACK_SUMMARY_PERIOD_PREFIX}prev_month" in callback_datas
        assert f"{CALLBACK_SUMMARY_PERIOD_PREFIX}other" in callback_datas


class TestBuildSummaryMonthsKeyboard:
    """Тесты построения меню выбора месяца для сводного отчёта."""

    def test_creates_buttons_for_months(self):
        """Создаёт кнопки для каждого месяца."""
        months = [(2024, 1), (2024, 2), (2023, 12)]
        keyboard = build_summary_months_keyboard(available_months=months)

        assert len(keyboard.inline_keyboard) == 3

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        months = [(2024, 3)]
        keyboard = build_summary_months_keyboard(available_months=months)

        assert keyboard.inline_keyboard[0][0].callback_data == f"{CALLBACK_SUMMARY_MONTH_PREFIX}2024:3"

    def test_button_text_contains_month_name(self):
        """Текст кнопки содержит название месяца."""
        months = [(2024, 1)]
        keyboard = build_summary_months_keyboard(available_months=months)

        assert "Январь" in keyboard.inline_keyboard[0][0].text
        assert "2024" in keyboard.inline_keyboard[0][0].text


class TestFormatSummaryReport:
    """Тесты форматирования сводного отчёта."""

    def test_empty_costs(self):
        """Пустой отчёт показывает сообщение о отсутствии данных."""
        report = format_summary_report({}, {}, year=2024, month=1)

        assert "Январь 2024" in report
        assert "Нет расходов" in report

    def test_report_with_single_user(self):
        """Отчёт с одним пользователем."""
        user_totals = {123: Decimal("100")}
        user_names = {123: "Alice"}
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        assert "<b>Январь 2024</b>" in report
        assert "<b>Всего:</b> 100" in report
        assert "Alice: 100" in report
        # Один пользователь - никто не должен платить
        assert "надо заплатить" not in report

    def test_report_with_two_users_equal(self):
        """Отчёт с двумя пользователями с равными расходами."""
        user_totals = {123: Decimal("100"), 456: Decimal("100")}
        user_names = {123: "Alice", 456: "Bob"}
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        assert "<b>Всего:</b> 200" in report
        # Равные расходы - никто не должен платить
        assert "надо заплатить" not in report

    def test_report_with_two_users_unequal(self):
        """Отчёт с двумя пользователями с неравными расходами."""
        user_totals = {123: Decimal("100"), 456: Decimal("50")}
        user_names = {123: "Alice", 456: "Bob"}
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        assert "<b>Всего:</b> 150" in report
        # Alice потратила 100, Bob 50. Среднее 75.
        # Bob должен заплатить 25
        assert "Bob:" in report
        assert "надо заплатить 25" in report
        assert "Alice: 100" in report
        assert "Bob: 50" in report

    def test_report_with_three_users(self):
        """Отчёт с тремя пользователями."""
        user_totals = {123: Decimal("120"), 456: Decimal("60"), 789: Decimal("0")}
        user_names = {123: "Alice", 456: "Bob", 789: "Carol"}
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        assert "<b>Всего:</b> 180" in report
        # Среднее = 60. Alice +60, Bob 0, Carol -60
        # Carol должна заплатить 60
        assert "надо заплатить 60" in report

    def test_users_sorted_by_amount(self):
        """Пользователи отсортированы по сумме убывания."""
        user_totals = {123: Decimal("50"), 456: Decimal("100"), 789: Decimal("25")}
        user_names = {123: "Alice", 456: "Bob", 789: "Carol"}
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        lines = report.split("\n")
        user_lines = [line for line in lines if ": " in line and "надо заплатить" not in line and "Всего" not in line]
        # Bob (100), Alice (50), Carol (25)
        assert "Bob" in user_lines[0]
        assert "Alice" in user_lines[1]
        assert "Carol" in user_lines[2]

    def test_unknown_user_shows_id(self):
        """Неизвестный пользователь показывается по ID."""
        user_totals = {123: Decimal("100")}
        user_names: dict[int, str] = {}  # Нет имени для 123
        report = format_summary_report(user_totals, user_names, year=2024, month=1)

        assert "123: 100" in report


class TestHandleSummary:
    """Тесты обработчика 'Сводная'."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_SUMMARY
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.answer = AsyncMock()

        await handle_summary(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_period_selection(self, callback):
        """Показывает выбор периода."""
        await handle_summary(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        call_kwargs = callback.message.answer.call_args.kwargs
        assert "reply_markup" in call_kwargs


class TestHandleSummaryPeriodSelection:
    """Тесты обработчика выбора периода для сводного отчёта."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_this_month_shows_report(self, callback):
        """Выбор 'Этот месяц' показывает сводный отчёт."""
        callback.data = f"{CALLBACK_SUMMARY_PERIOD_PREFIX}this_month"

        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_all_users_costs_by_month") as mock_get_costs,
            patch("bot.routers.menu.get_all_users") as mock_get_all_users,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = {123: Decimal("100")}
            mock_get_all_users.return_value = []

            await handle_summary_period_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_prev_month_shows_report(self, callback):
        """Выбор 'Прошлый месяц' показывает сводный отчёт."""
        callback.data = f"{CALLBACK_SUMMARY_PERIOD_PREFIX}prev_month"

        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_all_users_costs_by_month") as mock_get_costs,
            patch("bot.routers.menu.get_all_users") as mock_get_all_users,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = {123: Decimal("100")}
            mock_get_all_users.return_value = []

            await handle_summary_period_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_other_shows_months_list(self, callback):
        """Выбор 'Другие месяцы' показывает список месяцев."""
        callback.data = f"{CALLBACK_SUMMARY_PERIOD_PREFIX}other"

        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_available_months") as mock_get_months,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_months.return_value = [(2024, 1), (2024, 2)]

            await handle_summary_period_selection(callback)

            callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_period_returns_error(self, callback):
        """Неизвестный тип периода показывает ошибку."""
        callback.data = f"{CALLBACK_SUMMARY_PERIOD_PREFIX}unknown_period"

        await handle_summary_period_selection(callback)

        callback.answer.assert_called_once_with("Неизвестный период")


class TestHandleSummaryMonthSelection:
    """Тесты обработчика выбора месяца для сводного отчёта."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.answer = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = f"{CALLBACK_SUMMARY_MONTH_PREFIX}2024:1"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_shows_summary_report(self, callback):
        """Показывает сводный отчёт за выбранный месяц."""
        mock_session = AsyncMock()

        with (
            patch("bot.routers.menu.get_session") as mock_get_session,
            patch("bot.routers.menu.get_all_users_costs_by_month") as mock_get_costs,
            patch("bot.routers.menu.get_all_users") as mock_get_all_users,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_costs.return_value = {123: Decimal("100"), 456: Decimal("50")}
            mock_get_all_users.return_value = []

            await handle_summary_month_selection(callback)

            callback.answer.assert_called_once()
            callback.message.answer.assert_called_once()

            response = callback.message.answer.call_args[0][0]
            assert "Январь 2024" in response

    @pytest.mark.asyncio
    async def test_returns_early_without_data(self):
        """Выходит если callback.data пустой."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = None
        cb.answer = AsyncMock()

        await handle_summary_month_selection(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_returns_error(self, callback):
        """Неверный формат callback_data показывает ошибку."""
        callback.data = f"{CALLBACK_SUMMARY_MONTH_PREFIX}invalid"

        await handle_summary_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_year_returns_error(self, callback):
        """Некорректный год показывает ошибку."""
        callback.data = f"{CALLBACK_SUMMARY_MONTH_PREFIX}not_a_year:1"

        await handle_summary_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_month_returns_error(self, callback):
        """Некорректный месяц показывает ошибку."""
        callback.data = f"{CALLBACK_SUMMARY_MONTH_PREFIX}2024:not_a_month"

        await handle_summary_month_selection(callback)

        callback.answer.assert_called_once_with("Ошибка")
