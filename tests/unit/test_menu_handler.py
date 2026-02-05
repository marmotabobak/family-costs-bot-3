"""Тесты для роутера меню."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.routers.menu import (
    CALLBACK_DISABLE_PAST,
    CALLBACK_ENTER_PAST,
    CALLBACK_ENTER_PAST_MONTH,
    CALLBACK_ENTER_PAST_YEAR,
    CALLBACK_MONTH_PREFIX,
    CALLBACK_MY_COSTS,
    CALLBACK_PERIOD_PREFIX,
    CALLBACK_USER_COSTS_PREFIX,
    build_disable_past_keyboard,
    build_menu_keyboard,
    build_months_keyboard,
    build_past_months_keyboard,
    build_past_years_keyboard,
    build_period_keyboard,
    format_month_report,
    handle_disable_past,
    handle_enter_past,
    handle_enter_past_month,
    handle_month_selection,
    handle_my_costs,
    handle_period_selection,
    handle_user_costs,
    menu_command,
)


class TestBuildMenuKeyboard:
    """Тесты построения главного меню."""

    def test_empty_user_list(self):
        """Пустой список пользователей - только кнопка 'Мои расходы'."""
        keyboard = build_menu_keyboard(current_user_id=123, user_names={})

        assert len(keyboard.inline_keyboard) == 1
        assert keyboard.inline_keyboard[0][0].text == "📊 Мои расходы"
        assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_MY_COSTS

    def test_current_user_excluded(self):
        """Текущий пользователь не показывается в списке."""
        keyboard = build_menu_keyboard(current_user_id=123, user_names={123: "Alice", 456: "Bob", 789: "Carol"})

        assert len(keyboard.inline_keyboard) == 3

        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" not in callback_datas

    def test_all_users_shown(self):
        """Все пользователи кроме текущего показаны."""
        keyboard = build_menu_keyboard(current_user_id=100, user_names={123: "Alice", 456: "Bob", 789: "Carol"})

        assert len(keyboard.inline_keyboard) == 4

        callback_datas = [row[0].callback_data for row in keyboard.inline_keyboard[1:]]
        assert f"{CALLBACK_USER_COSTS_PREFIX}123" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}456" in callback_datas
        assert f"{CALLBACK_USER_COSTS_PREFIX}789" in callback_datas


class TestBuildPeriodKeyboard:
    """Тесты построения меню выбора периода."""

    def test_has_four_buttons_for_own(self):
        """Клавиатура содержит 4 кнопки для своих расходов (3 периода + ввод за другой месяц)."""
        keyboard = build_period_keyboard(user_id=123, is_own=True)

        assert len(keyboard.inline_keyboard) == 4
        # Последняя кнопка — "Внести расходы за другой месяц"
        assert "Внести расходы за другой месяц" in keyboard.inline_keyboard[3][0].text

    def test_has_three_buttons_for_other(self):
        """Клавиатура содержит 3 кнопки для чужих расходов (без ввода за другой месяц)."""
        keyboard = build_period_keyboard(user_id=123, is_own=False)

        assert len(keyboard.inline_keyboard) == 3

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        keyboard = build_period_keyboard(user_id=456, is_own=False)

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


# ========== Тесты для ввода расходов за другой месяц ==========


class TestBuildPastYearsKeyboard:
    """Тесты построения меню выбора года для ввода в прошлое."""

    def test_has_two_years(self):
        """Клавиатура содержит текущий и прошлый год."""
        keyboard = build_past_years_keyboard()

        assert len(keyboard.inline_keyboard) == 2

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        keyboard = build_past_years_keyboard()

        for row in keyboard.inline_keyboard:
            cb = row[0].callback_data
            assert cb is not None
            assert cb.startswith(CALLBACK_ENTER_PAST_YEAR)


class TestBuildPastMonthsKeyboard:
    """Тесты построения меню выбора месяца для ввода в прошлое."""

    def test_past_year_shows_all_months(self):
        """Для прошлого года показываются все 12 месяцев."""
        from datetime import datetime

        past_year = datetime.now().year - 1

        keyboard = build_past_months_keyboard(past_year)

        # Подсчитываем общее количество кнопок во всех рядах
        total_buttons = sum(len(row) for row in keyboard.inline_keyboard)
        assert total_buttons == 12

    def test_current_year_shows_only_past_months(self):
        """Для текущего года показываются только прошлые месяцы."""
        from datetime import datetime

        current_year = datetime.now().year
        current_month = datetime.now().month

        keyboard = build_past_months_keyboard(current_year)

        total_buttons = sum(len(row) for row in keyboard.inline_keyboard)
        # Должно быть current_month - 1 кнопок (не включая текущий месяц)
        assert total_buttons == current_month - 1

    def test_callback_data_format(self):
        """Проверка формата callback_data."""
        keyboard = build_past_months_keyboard(2024)

        for row in keyboard.inline_keyboard:
            for btn in row:
                cb = btn.callback_data
                assert cb is not None
                assert cb.startswith(CALLBACK_ENTER_PAST_MONTH)
                assert "2024:" in cb


class TestBuildDisablePastKeyboard:
    """Тесты построения кнопки отключения режима."""

    def test_has_one_button(self):
        """Клавиатура содержит одну кнопку."""
        keyboard = build_disable_past_keyboard()

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1

    def test_callback_data(self):
        """Проверка callback_data."""
        keyboard = build_disable_past_keyboard()

        assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_DISABLE_PAST

    def test_button_text(self):
        """Проверка текста кнопки."""
        keyboard = build_disable_past_keyboard()

        assert "Отключить прошлое" in keyboard.inline_keyboard[0][0].text


class TestHandleEnterPast:
    """Тесты обработчика начала ввода в прошлое."""

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
        cb.data = CALLBACK_ENTER_PAST
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_shows_year_selection(self, callback):
        """Показывает выбор года."""
        await handle_enter_past(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        call_args = callback.message.answer.call_args
        assert "Выберите год" in call_args[0][0]
        assert "reply_markup" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.answer = AsyncMock()

        await handle_enter_past(cb)

        cb.answer.assert_not_called()


class TestHandleEnterPastYear:
    """Тесты обработчика выбора года для ввода в прошлое."""

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
        cb.data = f"{CALLBACK_ENTER_PAST_YEAR}2024"
        cb.answer = AsyncMock()

        return cb

    @pytest.mark.asyncio
    async def test_shows_months_selection(self, callback):
        """Показывает выбор месяца."""
        from bot.routers.menu import handle_enter_past_year

        await handle_enter_past_year(callback)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        call_args = callback.message.answer.call_args
        assert "2024" in call_args[0][0]
        assert "reply_markup" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery
        from bot.routers.menu import handle_enter_past_year

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.data = None
        cb.answer = AsyncMock()

        await handle_enter_past_year(cb)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_year_returns_error(self, callback):
        """Некорректный год показывает ошибку."""
        from bot.routers.menu import handle_enter_past_year

        callback.data = f"{CALLBACK_ENTER_PAST_YEAR}not_a_year"

        await handle_enter_past_year(callback)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_no_available_months_shows_alert(self, callback):
        """Если нет доступных прошлых месяцев, показывает предупреждение."""
        from bot.routers.menu import handle_enter_past_year

        # В январе текущего года нет прошлых месяцев
        callback.data = f"{CALLBACK_ENTER_PAST_YEAR}2026"

        with patch("bot.routers.menu.datetime") as mock_datetime:
            mock_now = MagicMock()
            mock_now.year = 2026
            mock_now.month = 1  # January
            mock_datetime.now.return_value = mock_now

            await handle_enter_past_year(callback)

            callback.answer.assert_called_once_with(
                "Нет доступных прошлых месяцев для этого года",
                show_alert=True,
            )


class TestHandleEnterPastMonth:
    """Тесты обработчика выбора месяца для ввода в прошлое."""

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
        cb.data = f"{CALLBACK_ENTER_PAST_MONTH}2024:6"
        cb.answer = AsyncMock()

        return cb

    @pytest.fixture
    def mock_state(self):
        """Фикстура FSMContext."""
        state = AsyncMock()
        state.update_data = AsyncMock()
        return state

    @pytest.mark.asyncio
    async def test_enables_past_mode(self, callback, mock_state):
        """Включает режим ввода в прошлое."""
        await handle_enter_past_month(callback, mock_state)

        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        # Проверяем что режим сохранён в FSM
        mock_state.update_data.assert_called_once_with(past_mode_year=2024, past_mode_month=6)

    @pytest.mark.asyncio
    async def test_shows_warning_message(self, callback, mock_state):
        """Показывает предупреждающее сообщение."""
        await handle_enter_past_month(callback, mock_state)

        response = callback.message.answer.call_args[0][0]
        assert "Внимание" in response
        assert "Июнь 2024" in response
        assert "1-е число" in response

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

        mock_state = AsyncMock()

        await handle_enter_past_month(cb, mock_state)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_format_returns_error(self, callback, mock_state):
        """Неверный формат callback_data показывает ошибку."""
        callback.data = f"{CALLBACK_ENTER_PAST_MONTH}invalid"

        await handle_enter_past_month(callback, mock_state)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_year_returns_error(self, callback, mock_state):
        """Некорректный год показывает ошибку."""
        callback.data = f"{CALLBACK_ENTER_PAST_MONTH}not_a_year:6"

        await handle_enter_past_month(callback, mock_state)

        callback.answer.assert_called_once_with("Ошибка")

    @pytest.mark.asyncio
    async def test_invalid_month_returns_error(self, callback, mock_state):
        """Некорректный месяц показывает ошибку."""
        callback.data = f"{CALLBACK_ENTER_PAST_MONTH}2024:not_a_month"

        await handle_enter_past_month(callback, mock_state)

        callback.answer.assert_called_once_with("Ошибка")


class TestHandleDisablePast:
    """Тесты обработчика отключения режима ввода в прошлое."""

    @pytest.fixture
    def callback(self):
        """Фикстура CallbackQuery."""
        from aiogram.types import CallbackQuery, Message, User

        user = MagicMock(spec=User)
        user.id = 123

        msg = MagicMock(spec=Message)
        msg.edit_text = AsyncMock()

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.data = CALLBACK_DISABLE_PAST
        cb.answer = AsyncMock()

        return cb

    @pytest.fixture
    def mock_state(self):
        """Фикстура FSMContext."""
        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={
                "past_mode_year": 2024,
                "past_mode_month": 6,
            }
        )
        state.set_data = AsyncMock()
        return state

    @pytest.mark.asyncio
    async def test_disables_past_mode(self, callback, mock_state):
        """Отключает режим ввода в прошлое."""
        await handle_disable_past(callback, mock_state)

        callback.answer.assert_called_once()
        mock_state.set_data.assert_called_once()

        # Проверяем что past_mode_* удалены из данных
        new_data = mock_state.set_data.call_args[0][0]
        assert "past_mode_year" not in new_data
        assert "past_mode_month" not in new_data

    @pytest.mark.asyncio
    async def test_shows_confirmation_message(self, callback, mock_state):
        """Показывает подтверждающее сообщение."""
        await handle_disable_past(callback, mock_state)

        callback.message.edit_text.assert_called_once()
        response = callback.message.edit_text.call_args[0][0]
        assert "Прошлое ушло" in response
        assert "сегодня" in response

    @pytest.mark.asyncio
    async def test_returns_early_without_user(self):
        """Выходит если нет from_user."""
        from aiogram.types import CallbackQuery

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.answer = AsyncMock()

        mock_state = AsyncMock()

        await handle_disable_past(cb, mock_state)

        cb.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_state(self, callback):
        """Корректно обрабатывает пустой state."""
        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={})
        mock_state.set_data = AsyncMock()

        await handle_disable_past(callback, mock_state)

        callback.answer.assert_called_once()
        # Не должен вызывать set_data если нет past_mode_*
        mock_state.set_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_preserves_other_state_data(self, callback):
        """Сохраняет другие данные в state при отключении режима."""
        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(
            return_value={
                "past_mode_year": 2024,
                "past_mode_month": 6,
                "other_key": "other_value",
            }
        )
        mock_state.set_data = AsyncMock()

        await handle_disable_past(callback, mock_state)

        new_data = mock_state.set_data.call_args[0][0]
        assert "other_key" in new_data
        assert new_data["other_key"] == "other_value"


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
