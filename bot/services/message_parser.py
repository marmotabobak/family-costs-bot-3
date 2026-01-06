import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cost:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class ParseResult:
    valid_lines: list[Cost]
    invalid_lines: list[str]


MESSAGE_RE = re.compile(r"^\s*(?P<text>.+?)\s+(?P<amount>[+-]?\d+(?:[.,]\d+)?)\s*$")

# Лимиты для защиты от DoS атак
MAX_MESSAGE_LENGTH = 4096  # Telegram limit
MAX_LINE_LENGTH = 500
MAX_LINES = 100


def parse_message(message: str | None) -> ParseResult | None:
    if not message:
        return None

    # Проверка общей длины сообщения
    if len(message) > MAX_MESSAGE_LENGTH:
        logger.warning("Message too long: %d characters", len(message))
        return None

    lines = message.splitlines()

    # Проверка количества строк
    if len(lines) > MAX_LINES:
        logger.warning("Too many lines: %d", len(lines))
        return None

    valid_costs: list[Cost] = []
    invalid_costs: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Проверка длины строки
        if len(line) > MAX_LINE_LENGTH:
            logger.debug("Line too long: %r", line[:100])
            invalid_costs.append(raw_line[:100] + "...")
            continue

        match = MESSAGE_RE.match(line)
        if not match:
            logger.debug("Invalid format: %r", raw_line)
            invalid_costs.append(raw_line)
            continue

        try:
            amount = Decimal(match.group("amount").replace(",", "."))
        except InvalidOperation:
            logger.debug("Invalid amount: %r", raw_line)
            invalid_costs.append(raw_line)
            continue

        cost = Cost(name=match.group("text").strip(), amount=amount)
        valid_costs.append(cost)

    if not valid_costs:
        return None

    return ParseResult(valid_lines=valid_costs, invalid_lines=invalid_costs)
