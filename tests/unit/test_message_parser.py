from decimal import Decimal, InvalidOperation
from unittest.mock import patch

import pytest

from bot.services.message_parser import Cost, ParseResult, parse_message
from bot.exceptions import MessageMaxLengthExceed, MessageMaxLineLengthExceed, MessageMaxLinesCountExceed
from bot.constants import MAX_MESSAGE_LENGTH, MAX_MESSAGE_LINES_COUNT, MAX_MESSAGE_LINE_LENGTH

class TestParseMessageReturnsNone:
    def test_none_input(self):
        assert parse_message(None) is None

    def test_empty_string(self):
        assert parse_message("") is None

    def test_whitespace_only(self):
        assert parse_message("   \n\t\n  ") is None

    def test_no_amount(self):
        assert parse_message("продукты") is None


class TestParseMessageValidSingleLine:
    def test_simple_integer(self):
        result = parse_message("Продукты 100")
        assert result == ParseResult(
            valid_lines=[Cost(name="Продукты", amount=Decimal("100"))],
            invalid_lines=[],
        )

    def test_decimal_with_dot(self):
        result = parse_message("вода из Лавки 123.56")
        assert result == ParseResult(
            valid_lines=[Cost(name="вода из Лавки", amount=Decimal("123.56"))],
            invalid_lines=[],
        )

    def test_decimal_with_comma(self):
        result = parse_message("морковь 123,00")
        assert result == ParseResult(
            valid_lines=[Cost(name="морковь", amount=Decimal("123.00"))],
            invalid_lines=[],
        )

    def test_negative_amount(self):
        result = parse_message("корректировка расхода -500.24")
        assert result == ParseResult(
            valid_lines=[Cost(name="корректировка расхода", amount=Decimal("-500.24"))],
            invalid_lines=[],
        )

    def test_positive_sign(self):
        result = parse_message("возврат +200")
        assert result == ParseResult(
            valid_lines=[Cost(name="возврат", amount=Decimal("200"))],
            invalid_lines=[],
        )

    def test_leading_whitespace(self):
        result = parse_message("   Продукты 100")
        assert result == ParseResult(
            valid_lines=[Cost(name="Продукты", amount=Decimal("100"))],
            invalid_lines=[],
        )

    def test_trailing_whitespace(self):
        result = parse_message("Продукты 100   ")
        assert result == ParseResult(
            valid_lines=[Cost(name="Продукты", amount=Decimal("100"))],
            invalid_lines=[],
        )

    def test_multiple_spaces_between(self):
        result = parse_message("Продукты    100")
        assert result == ParseResult(
            valid_lines=[Cost(name="Продукты", amount=Decimal("100"))],
            invalid_lines=[],
        )

    def test_special_characters(self):
        result = parse_message("\\-.!#_@:`<>/ 123.45")
        assert result == ParseResult(
            valid_lines=[Cost(name="\\-.!#_@:`<>/", amount=Decimal("123.45"))],
            invalid_lines=[],
        )


class TestParseMessageMultipleLines:
    def test_multiple_valid_lines(self):
        message = """Продукты 100
вода 50.5
хлеб 30"""
        result = parse_message(message)
        assert result == ParseResult(
            valid_lines=[
                Cost(name="Продукты", amount=Decimal("100")),
                Cost(name="вода", amount=Decimal("50.5")),
                Cost(name="хлеб", amount=Decimal("30")),
            ],
            invalid_lines=[],
        )

    def test_with_empty_lines(self):
        message = """Продукты 100

вода 50"""
        result = parse_message(message)
        assert result == ParseResult(
            valid_lines=[
                Cost(name="Продукты", amount=Decimal("100")),
                Cost(name="вода", amount=Decimal("50")),
            ],
            invalid_lines=[],
        )


class TestParseMessageMixedLines:
    def test_valid_and_invalid_lines(self):
        message = """Продукты 100
invalid line
вода 50"""
        result = parse_message(message)
        assert result == ParseResult(
            valid_lines=[
                Cost(name="Продукты", amount=Decimal("100")),
                Cost(name="вода", amount=Decimal("50")),
            ],
            invalid_lines=["invalid line"],
        )

    def test_multiple_invalid_lines(self):
        message = """Продукты 100
no amount here
another bad line
вода 50"""
        result = parse_message(message)
        assert result == ParseResult(
            valid_lines=[
                Cost(name="Продукты", amount=Decimal("100")),
                Cost(name="вода", amount=Decimal("50")),
            ],
            invalid_lines=["no amount here", "another bad line"],
        )


class TestParseMessageEdgeCases:
    def test_long_description(self):
        result = parse_message("заказ из Озона №12345 с доставкой 234")
        assert result == ParseResult(
            valid_lines=[Cost(name="заказ из Озона №12345 с доставкой", amount=Decimal("234"))],
            invalid_lines=[],
        )

    def test_description_with_numbers(self):
        result = parse_message("заказ №123 100")
        assert result == ParseResult(
            valid_lines=[Cost(name="заказ №123", amount=Decimal("100"))],
            invalid_lines=[],
        )

    def test_zero_amount(self):
        result = parse_message("бесплатно 0")
        assert result == ParseResult(
            valid_lines=[Cost(name="бесплатно", amount=Decimal("0"))],
            invalid_lines=[],
        )

    def test_large_amount(self):
        result = parse_message("квартира 10000000.99")
        assert result == ParseResult(
            valid_lines=[Cost(name="квартира", amount=Decimal("10000000.99"))],
            invalid_lines=[],
        )


class TestParseMessageDecimalError:
    """Тест обработки ошибки InvalidOperation (защитный код)."""

    def test_invalid_decimal_operation(self):
        """Если Decimal выбросит InvalidOperation, строка попадёт в invalid_lines."""
        with patch(
            "bot.services.message_parser.Decimal",
            side_effect=[InvalidOperation("test"), Decimal("50")],
        ):
            result = parse_message("первый 100\nвторой 50")

        assert result == ParseResult(
            valid_lines=[Cost(name="второй", amount=Decimal("50"))],
            invalid_lines=["первый 100"],
        )


class TestMessageLimits:
    """Тесты лимитов на длину сообщений."""

    def test_message_too_long_raises_exception(self):
        """Слишком длинное сообщение вызывает исключение MessageMaxLengthExceed."""
        # Создаем сообщение > MAX_MESSAGE_LENGTH символов
        long_message = "Продукты 100\n" * 500
        assert len(long_message) > MAX_MESSAGE_LENGTH

        with pytest.raises(MessageMaxLengthExceed):
            parse_message(long_message)

    def test_too_many_lines_raises_exception(self):
        """Слишком много строк вызывает исключение MessageMaxLengthExceed."""
        # Создаем > MAX_MESSAGE_LINES_COUNT строк
        many_lines = "\n".join([f"Товар{i} 100" for i in range(MAX_MESSAGE_LINES_COUNT + 1)])
        assert len(many_lines.splitlines()) > MAX_MESSAGE_LINES_COUNT
        
        with pytest.raises(MessageMaxLinesCountExceed):
            parse_message(many_lines)

    def test_line_too_long_raises_exception(self):
        """Слишком длинная строка помечается как невалидная."""
        # Создаем строку > MAX_MESSAGE_LINE_LENGTH символов
        long_line = "Товар с очень длинным названием " * 50 + " 100"
        assert len(long_line) > MAX_MESSAGE_LINE_LENGTH
        
        with pytest.raises(MessageMaxLineLengthExceed):
            parse_message(long_line)

    def test_max_message_length_boundary(self):
        """Сообщение ровно MAX_MESSAGE_LENGTH парсится нормально."""
        # Создаем сообщение ровно 4096 символов, но < 100 строк
        # Используем длинные строки, чтобы не превысить лимит строк
        line = "Товар с длинным названием для теста " + "X" * 30 + " 100\n"
        num_lines = MAX_MESSAGE_LENGTH // len(line)
        message = line * num_lines
        # Обрезаем до ровно MAX_MESSAGE_LENGTH
        message = message[:MAX_MESSAGE_LENGTH]
        
        # Убеждаемся что строк < 100
        assert len(message.splitlines()) < MAX_MESSAGE_LINES_COUNT
        
        result = parse_message(message)
        
        # Должно распарситься (граница включительно)
        assert result is not None

    def test_max_lines_boundary(self):
        """Сообщение ровно MAX_MESSAGE_LINES_COUNT парсится нормально."""
        # Создаем ровно MAX_MESSAGE_LINES_COUNT строк
        message = "\n".join([f"Товар{i} 100" for i in range(MAX_MESSAGE_LINES_COUNT)])
        
        result = parse_message(message)
        
        # Должно распарситься
        assert result is not None
        assert len(result.valid_lines) == MAX_MESSAGE_LINES_COUNT

    def test_max_line_length_boundary(self):
        """Строка ровно MAX_LINE_LENGTH парсится нормально."""
        # Создаем строку ровно 500 символов (включая "Товар " и " 100")
        item_name = "Т" * (MAX_MESSAGE_LINE_LENGTH - len("Товар  100"))
        line = f"Товар {item_name} 100"
        assert len(line) == MAX_MESSAGE_LINE_LENGTH
        
        result = parse_message(line)
        
        # Должно распарситься
        assert result is not None
        assert len(result.valid_lines) == 1
