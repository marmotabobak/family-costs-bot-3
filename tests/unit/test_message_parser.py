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


class TestParseMessageUnicodeAndSpecialCharacters:
    """Тесты Unicode символов и специальных символов."""

    def test_unicode_characters(self):
        """Unicode символы в названии расхода."""
        result = parse_message("Продукты 🍎 100")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert "🍎" in result.valid_lines[0].name

    def test_emoji_in_name(self):
        """Emoji в названии расхода."""
        result = parse_message("Покупка 😊 200")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert "😊" in result.valid_lines[0].name

    def test_special_characters_in_name(self):
        """Специальные символы в названии."""
        result = parse_message("заказ #123 @test 100")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert "#123" in result.valid_lines[0].name
        assert "@test" in result.valid_lines[0].name

    def test_html_characters(self):
        """HTML символы в названии (должны парситься, но не выполняться)."""
        result = parse_message("<script>alert('xss')</script> 100")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert "<script>" in result.valid_lines[0].name

    def test_cyrillic_and_latin_mixed(self):
        """Смешанные кириллица и латиница."""
        result = parse_message("Product товар 100")
        assert result is not None
        assert len(result.valid_lines) == 1

    def test_chinese_characters(self):
        """Китайские символы."""
        result = parse_message("商品 100")
        assert result is not None
        assert len(result.valid_lines) == 1

    def test_arabic_characters(self):
        """Арабские символы."""
        result = parse_message("منتج 100")
        assert result is not None
        assert len(result.valid_lines) == 1


class TestParseMessageDecimalEdgeCases:
    """Тесты граничных случаев для десятичных чисел."""

    def test_decimal_at_start(self):
        """Десятичная точка в начале числа должна быть невалидной."""
        # Regex требует хотя бы одну цифру перед точкой
        result = parse_message("Product .5")
        assert result is None or len(result.invalid_lines) > 0

    def test_decimal_at_end(self):
        """Десятичная точка в конце числа должна быть невалидной."""
        # Regex требует цифры после точки или отсутствие точки
        result = parse_message("Product 5.")
        assert result is None or len(result.invalid_lines) > 0

    def test_multiple_decimal_separators_fails(self):
        """Множественные десятичные разделители должны быть невалидными."""
        result = parse_message("Product 12.34.56")
        assert result is None or "12.34.56" in (result.invalid_lines if result else [])

    def test_scientific_notation_fails(self):
        """Научная нотация должна быть невалидной."""
        result = parse_message("Product 1e5")
        assert result is None or "1e5" in (result.invalid_lines if result else [])

    def test_very_large_decimal(self):
        """Очень большое десятичное число."""
        result = parse_message("Product 999999999999999.999999999999")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert isinstance(result.valid_lines[0].amount, Decimal)

    def test_leading_zeros(self):
        """Ведущие нули в числе."""
        result = parse_message("Product 00100")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("100")

    def test_trailing_zeros(self):
        """Завершающие нули в десятичном числе."""
        result = parse_message("Product 100.00")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("100.00")

    def test_negative_zero(self):
        """Отрицательный ноль."""
        result = parse_message("Product -0")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("-0")

    def test_very_small_decimal(self):
        """Очень маленькое десятичное число."""
        result = parse_message("Product 0.000000000001")
        assert result is not None
        assert len(result.valid_lines) == 1


class TestParseMessageCostNameEdgeCases:
    """Тесты граничных случаев для названий расходов."""

    def test_cost_name_with_only_spaces(self):
        """Название с только пробелами должно быть невалидным."""
        result = parse_message("   100")
        # Это может быть интерпретировано как валидное (пустое имя) или невалидное
        # Проверяем что парсер обрабатывает это корректно
        assert result is None or len(result.valid_lines) == 0

    def test_cost_name_empty_after_strip(self):
        """Название пустое после strip."""
        result = parse_message("  100")
        # Может быть валидным с пустым именем или невалидным
        assert result is None or len(result.valid_lines) == 0

    def test_cost_name_with_tabs(self):
        """Табы вместо пробелов обрабатываются как пробелы (валидно)."""
        # Regex \s+ обрабатывает табы как пробелы
        result = parse_message("Product\t100")
        assert result is not None
        assert len(result.valid_lines) == 1
        assert result.valid_lines[0].name == "Product"
        assert result.valid_lines[0].amount == Decimal("100")

    def test_cost_name_with_newlines(self):
        """Название с переносами строк должно быть невалидным."""
        result = parse_message("Line1\nLine2 100")
        # Должно быть невалидным или разбито на строки
        assert result is None or len(result.invalid_lines) > 0 or len(result.valid_lines) == 0

    def test_very_long_cost_name(self):
        """Очень длинное название (99 символов)."""
        long_name = "A" * (MAX_MESSAGE_LINE_LENGTH - 10)  # Оставляем место для " 100"
        line = f"{long_name} 100"
        assert len(line) <= MAX_MESSAGE_LINE_LENGTH
        
        result = parse_message(line)
        assert result is not None
        assert len(result.valid_lines) == 1

    def test_cost_name_with_many_spaces(self):
        """Множественные пробелы в названии."""
        result = parse_message("Product    with    spaces    100")
        assert result is not None
        assert len(result.valid_lines) == 1
        # Пробелы должны быть сохранены в имени
        assert "   " in result.valid_lines[0].name or "  " in result.valid_lines[0].name


class TestParseMessageLineEndings:
    """Тесты различных окончаний строк."""

    def test_windows_line_endings(self):
        """Windows окончания строк (\r\n)."""
        message = "Product1 100\r\nProduct2 200"
        result = parse_message(message)
        assert result is not None
        assert len(result.valid_lines) == 2

    def test_mac_line_endings(self):
        """Mac окончания строк (\r)."""
        message = "Product1 100\rProduct2 200"
        result = parse_message(message)
        assert result is not None
        assert len(result.valid_lines) == 2

    def test_unix_line_endings(self):
        """Unix окончания строк (\n)."""
        message = "Product1 100\nProduct2 200"
        result = parse_message(message)
        assert result is not None
        assert len(result.valid_lines) == 2

    def test_mixed_line_endings(self):
        """Смешанные окончания строк."""
        message = "Product1 100\nProduct2 200\r\nProduct3 300"
        result = parse_message(message)
        assert result is not None
        assert len(result.valid_lines) == 3


class TestParseMessageAmountEdgeCases:
    """Тесты граничных случаев для сумм."""

    def test_very_large_amount(self):
        """Очень большая сумма."""
        result = parse_message("Product 999999999999999.99")
        assert result is not None
        assert len(result.valid_lines) == 1

    def test_very_small_amount(self):
        """Очень маленькая сумма."""
        result = parse_message("Product 0.01")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("0.01")

    def test_amount_with_many_decimal_places(self):
        """Сумма с большим количеством десятичных знаков."""
        result = parse_message("Product 123.12345678901234567890")
        assert result is not None
        assert len(result.valid_lines) == 1

    def test_negative_large_amount(self):
        """Отрицательная большая сумма."""
        result = parse_message("Correction -999999999999999.99")
        assert result is not None
        assert result.valid_lines[0].amount < 0

    def test_amount_with_comma_separator(self):
        """Сумма с запятой как разделитель."""
        result = parse_message("Product 123,45")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("123.45")

    def test_amount_with_dot_separator(self):
        """Сумма с точкой как разделитель."""
        result = parse_message("Product 123.45")
        assert result is not None
        assert result.valid_lines[0].amount == Decimal("123.45")


class TestParseMessageCurrencyBracket:
    """Task 3.1 — Optional currency bracket ``[CUR]`` in message lines."""

    def test_no_bracket_currency_code_is_none(self):
        """'coffee 250' — no bracket → currency_code is None."""
        result = parse_message("coffee 250")
        assert result is not None
        cost = result.valid_lines[0]
        assert cost.currency_code is None
        assert cost.name == "coffee"
        assert cost.amount == Decimal("250")

    def test_valid_bracket_extracted(self):
        """'lunch 12.50 [USD]' → currency_code='USD'."""
        result = parse_message("lunch 12.50 [USD]")
        assert result is not None
        cost = result.valid_lines[0]
        assert cost.currency_code == "USD"
        assert cost.name == "lunch"
        assert cost.amount == Decimal("12.50")

    def test_lowercase_bracket_invalid_line(self):
        """'lunch 12.50 [usd]' → not matched (lowercase letters not allowed)."""
        result = parse_message("lunch 12.50 [usd]")
        # The line does not match MESSAGE_RE → treated as invalid
        # If the whole message has no valid lines, result is None
        assert result is None or len(result.valid_lines) == 0

    def test_four_char_bracket_invalid_line(self):
        """'lunch 12.50 [USDD]' → not matched (4 chars not 3)."""
        result = parse_message("lunch 12.50 [USDD]")
        assert result is None or len(result.valid_lines) == 0

    def test_name_with_uppercase_suffix_no_bracket(self):
        """'foo BAR 10' — name ends in uppercase word but no brackets → currency_code=None."""
        result = parse_message("foo BAR 10")
        assert result is not None
        cost = result.valid_lines[0]
        assert cost.currency_code is None
        assert cost.name == "foo BAR"
        assert cost.amount == Decimal("10")

    def test_rub_bracket(self):
        """'продукты 500 [RUB]' → currency_code='RUB'."""
        result = parse_message("продукты 500 [RUB]")
        assert result is not None
        cost = result.valid_lines[0]
        assert cost.currency_code == "RUB"

    def test_negative_amount_with_bracket(self):
        """'корректировка -100 [USD]' → amount=-100, currency_code='USD'."""
        result = parse_message("корректировка -100 [USD]")
        assert result is not None
        cost = result.valid_lines[0]
        assert cost.amount == Decimal("-100")
        assert cost.currency_code == "USD"
