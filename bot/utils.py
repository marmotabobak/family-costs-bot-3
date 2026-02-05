from decimal import Decimal


def format_amount(amount: Decimal) -> str:
    """Format amount with non-breaking space as thousands separator.

    Omits .00 for whole numbers; keeps two decimal places otherwise.
    Examples: 1234.56 → "1 234.56", 1000 → "1 000", 100.00 → "100"
    """
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(",", "\u00a0")
    s = f"{amount:.2f}"
    int_part, frac_part = s.split(".")
    return f"{int(int_part):,}".replace(",", "\u00a0") + "." + frac_part


def pluralize(n: int, form1: str, form2: str, form5: str) -> str:
    """Склонение существительных по числу (1 расход, 2 расхода, 5 расходов)."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return form1
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return form2
    return form5
