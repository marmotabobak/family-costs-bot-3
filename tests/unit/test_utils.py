from decimal import Decimal

from bot.utils import format_amount, format_cost_line, pluralize


class TestFormatAmount:
    """Тесты форматирования сумм."""

    def test_whole_number_small(self):
        """Целое число < 1000 — без разделителя, без .00."""
        assert format_amount(Decimal("100")) == "100"

    def test_whole_number_thousands(self):
        """Целое число с разделителем тысяч."""
        assert format_amount(Decimal("1000")) == "1\u00a0000"

    def test_whole_number_millions(self):
        """Число в миллионах."""
        assert format_amount(Decimal("1000000")) == "1\u00a0000\u00a0000"

    def test_whole_number_from_decimal_with_zeros(self):
        """100.00 — дробная часть .00 не показывается."""
        assert format_amount(Decimal("100.00")) == "100"

    def test_decimal_two_places(self):
        """Число с двумя знаками после запятой."""
        assert format_amount(Decimal("100.50")) == "100.50"

    def test_decimal_with_thousands(self):
        """Число с тысячами и дробной частью."""
        assert format_amount(Decimal("1234.56")) == "1\u00a0234.56"

    def test_decimal_trailing_zero(self):
        """100.10 — сохраняет второй нуль."""
        assert format_amount(Decimal("100.10")) == "100.10"

    def test_negative_whole(self):
        """Отрицательное целое число."""
        assert format_amount(Decimal("-50")) == "-50"

    def test_negative_with_thousands(self):
        """Отрицательное число с тысячами."""
        assert format_amount(Decimal("-1234")) == "-1\u00a0234"

    def test_negative_decimal(self):
        """Отрицательное число с дробной частью."""
        assert format_amount(Decimal("-1234.56")) == "-1\u00a0234.56"

    def test_zero(self):
        """Ноль."""
        assert format_amount(Decimal("0")) == "0"

    def test_small_decimal(self):
        """Маленькое число с дробью."""
        assert format_amount(Decimal("0.01")) == "0.01"

    def test_custom_separator_underscore(self):
        """sep='_' используется в бот-сообщениях."""
        assert format_amount(Decimal("1000"), sep="_") == "1_000"
        assert format_amount(Decimal("1234.56"), sep="_") == "1_234.56"
        assert format_amount(Decimal("100"), sep="_") == "100"


class TestPluralize:
    """Тесты склонения существительных по числу."""

    def test_form1_singular(self):
        """1, 21, 31, 101... → расход"""
        expected = "расход"
        assert pluralize(1, "расход", "расхода", "расходов") == expected
        assert pluralize(21, "расход", "расхода", "расходов") == expected
        assert pluralize(101, "расход", "расхода", "расходов") == expected

    def test_form2_few(self):
        """2-4, 22-24, 32-34... → расхода"""
        expected = "расхода"
        assert pluralize(2, "расход", "расхода", "расходов") == expected
        assert pluralize(3, "расход", "расхода", "расходов") == expected
        assert pluralize(4, "расход", "расхода", "расходов") == expected
        assert pluralize(22, "расход", "расхода", "расходов") == expected
        assert pluralize(33, "расход", "расхода", "расходов") == expected
        assert pluralize(104, "расход", "расхода", "расходов") == expected

    def test_form5_many(self):
        """0, 5-20, 25-30, 111-114... → расходов"""
        expected = "расходов"
        assert pluralize(0, "расход", "расхода", "расходов") == expected
        assert pluralize(5, "расход", "расхода", "расходов") == expected
        assert pluralize(10, "расход", "расхода", "расходов") == expected
        assert pluralize(11, "расход", "расхода", "расходов") == expected
        assert pluralize(12, "расход", "расхода", "расходов") == expected
        assert pluralize(13, "расход", "расхода", "расходов") == expected
        assert pluralize(15, "расход", "расхода", "расходов") == expected
        assert pluralize(20, "расход", "расхода", "расходов") == expected
        assert pluralize(25, "расход", "расхода", "расходов") == expected
        assert pluralize(100, "расход", "расхода", "расходов") == expected
        assert pluralize(111, "расход", "расхода", "расходов") == expected
        assert pluralize(112, "расход", "расхода", "расходов") == expected

    def test_negative_numbers(self):
        """Отрицательные числа используют абсолютное значение."""
        assert pluralize(-1, "расход", "расхода", "расходов") == "расход"
        assert pluralize(-2, "расход", "расхода", "расходов") == "расхода"
        assert pluralize(-5, "расход", "расхода", "расходов") == "расходов"


class TestFormatCostLine:
    """Task 5.4 — format_cost_line helper."""

    def test_base_currency_no_bracket(self):
        """When currency_code == base_currency_code → no bracket shown."""
        line = format_cost_line(
            name="coffee",
            amount=Decimal("250"),
            currency_code="RUB",
            base_currency_code="RUB",
            base_amount=Decimal("250"),
        )
        assert line == "coffee: 250 RUB"

    def test_non_base_currency_shows_bracket(self):
        """Non-base currency shows [<base_amount> <BASE_CODE>]."""
        line = format_cost_line(
            name="lunch",
            amount=Decimal("10"),
            currency_code="USD",
            base_currency_code="RUB",
            base_amount=Decimal("970"),
        )
        assert line == "lunch: 10 USD [970 RUB]"

    def test_base_currency_thousands_formatting(self):
        """Thousands are formatted with _ separator in bot mode."""
        line = format_cost_line(
            name="rent",
            amount=Decimal("50000"),
            currency_code="RUB",
            base_currency_code="RUB",
            base_amount=Decimal("50000"),
        )
        assert line == "rent: 50_000 RUB"

    def test_non_base_thousands_in_base_amount(self):
        """Thousands in base_amount are also formatted."""
        line = format_cost_line(
            name="flight",
            amount=Decimal("1000"),
            currency_code="USD",
            base_currency_code="RUB",
            base_amount=Decimal("97000"),
        )
        assert line == "flight: 1_000 USD [97_000 RUB]"

    def test_non_base_base_amount_rounded_to_two_decimals(self):
        """base_amount is quantized to 2 decimal places."""
        line = format_cost_line(
            name="item",
            amount=Decimal("1"),
            currency_code="USD",
            base_currency_code="RUB",
            base_amount=Decimal("90.1234"),
        )
        assert "[90.12 RUB]" in line

    def test_negative_amount_non_base(self):
        """Negative amounts are formatted correctly."""
        line = format_cost_line(
            name="refund",
            amount=Decimal("-10"),
            currency_code="USD",
            base_currency_code="RUB",
            base_amount=Decimal("-970"),
        )
        assert line == "refund: -10 USD [-970 RUB]"
