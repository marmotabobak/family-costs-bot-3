from decimal import Decimal

from bot.utils import format_amount, pluralize


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
