from bot.utils import pluralize


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
