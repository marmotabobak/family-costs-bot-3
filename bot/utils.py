def pluralize(n: int, form1: str, form2: str, form5: str) -> str:
    """Склонение существительных по числу (1 расход, 2 расхода, 5 расходов)."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return form1
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return form2
    return form5
