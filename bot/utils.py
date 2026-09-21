from decimal import Decimal, ROUND_HALF_UP


def format_amount(amount: Decimal, sep: str = " ") -> str:
    """Format amount with thousands separator.

    Omits .00 for whole numbers; keeps two decimal places otherwise.
    Default sep is non-breaking space (web); bot passes sep="_".
    Examples: 1234.56 → "1 234.56", 1000 → "1 000", 100.00 → "100"
    """
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(",", sep)
    s = f"{amount:.2f}"
    int_part, frac_part = s.split(".")
    return f"{int(int_part):,}".replace(",", sep) + "." + frac_part


def pluralize(n: int, form1: str, form2: str, form5: str) -> str:
    """Склонение существительных по числу (1 расход, 2 расхода, 5 расходов)."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return form1
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return form2
    return form5


def format_cost_line(
    name: str,
    amount: Decimal,
    currency_code: str,
    base_currency_code: str,
    base_amount: Decimal,
) -> str:
    """Format a single cost line for bot output.

    Two cases:

    * **Base currency** (``currency_code == base_currency_code``):
      ``"<name>: <amount> <BASE_CODE>"``
    * **Non-base currency**:
      ``"<name>: <amount> <CUR_CODE> [<base_amount:.2f> <BASE_CODE>]"``

    ``format_amount`` is applied to the main *amount* with ``sep='_'``.
    For the base-converted amount, it is rounded to 2 decimal places using
    ``ROUND_HALF_UP`` and also formatted with ``sep='_'``.

    Args:
        name: human-readable cost name.
        amount: cost amount in *currency_code* units.
        currency_code: ISO code of the cost currency.
        base_currency_code: ISO code of the system base currency.
        base_amount: pre-computed cost amount in base-currency units.

    Returns:
        A formatted string ready for Telegram message output.
    """
    fmt_amount = format_amount(amount, sep="_")
    if currency_code == base_currency_code:
        return f"{name}: {fmt_amount} {base_currency_code}"
    base_rounded = base_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    fmt_base = format_amount(base_rounded, sep="_")
    return f"{name}: {fmt_amount} {currency_code} [{fmt_base} {base_currency_code}]"
