import logging
import html
from decimal import Decimal

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.exc import SQLAlchemyError

from bot.constants import (
    HELP_TEXT,
    MSG_DB_ERROR,
    MSG_PARSE_ERROR,
    MSG_MESSAGE_MAX_LENGTH,
    MSG_MESSAGE_MAX_LINE_LENGTH,
    MSG_MESSAGE_MAX_LINES_COUNT
)
from bot.db.dependencies import get_session
from bot.db.models import Currency
from bot.db.repositories.currencies import get_base_currency, list_currencies
from bot.db.repositories.messages import save_message
from bot.services.currency_rates import RateCache
from bot.services.message_parser import Cost, parse_message
from bot.utils import format_cost_line, pluralize
from bot.exceptions import MessageMaxLineLengthExceed, MessageMaxLengthExceed, MessageMaxLinesCountExceed


logger = logging.getLogger(__name__)
router = Router()

CALLBACK_CONFIRM = "confirm_save"
CALLBACK_CANCEL = "cancel_save"

# =====================
# FSM
# =====================

class SaveCostsStates(StatesGroup):
    waiting_confirmation = State()


# =====================
# KEYBOARDS
# =====================

def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, записать", callback_data=CALLBACK_CONFIRM),
            InlineKeyboardButton(text="❌ Нет, отменить", callback_data=CALLBACK_CANCEL),
        ]
    ])


# =====================
# HELPERS
# =====================

def esc(text: str) -> str:
    """HTML-экранирование пользовательского ввода."""
    return html.escape(text, quote=False)


def format_confirmation_message(
    valid_costs: list[Cost],
    invalid_lines: list[str],
    base_currency_code: str = "RUB",
    base_amounts: dict[int, Decimal] | None = None,
) -> str:
    """Build the pre-save confirmation message.

    Args:
        valid_costs: costs that parsed successfully.
        invalid_lines: raw lines that failed to parse or had unknown currencies.
        base_currency_code: ISO code of the base currency.
        base_amounts: mapping of index → base-amount for non-base costs;
            when ``None`` the plain amount is shown.
    """
    lines: list[str] = []

    if invalid_lines:
        lines.append("⚠️ <b>Не удалось распарсить строки:</b>")
        lines.append("")
        for line in invalid_lines:
            lines.append(f"• {esc(line)}")
        lines.append("")

    lines.append("<b>Успешно распарсены строки:</b>")
    lines.append("")
    for idx, cost in enumerate(valid_costs):
        cur_code = cost.currency_code or base_currency_code
        base_amount = (base_amounts or {}).get(idx, cost.amount)
        line_str = format_cost_line(
            name=cost.name,
            amount=cost.amount,
            currency_code=cur_code,
            base_currency_code=base_currency_code,
            base_amount=base_amount,
        )
        lines.append(f"• {esc(line_str)}")

    lines.append("")
    lines.append("Записать распарсенные строки?")

    return "\n".join(lines)


def format_success_message(
    costs: list[Cost],
    base_currency_code: str = "RUB",
    base_amounts: dict[int, Decimal] | None = None,
) -> str:
    """Build the post-save success message.

    Args:
        costs: costs that were saved.
        base_currency_code: ISO code of the base currency.
        base_amounts: mapping of index → base-amount for non-base costs.
    """
    count = len(costs)
    word = pluralize(count, "расход", "расхода", "расходов")

    lines = [f"✅ <b>Записано {count} {word}:</b>", ""]
    for idx, cost in enumerate(costs):
        cur_code = cost.currency_code or base_currency_code
        base_amount = (base_amounts or {}).get(idx, cost.amount)
        line_str = format_cost_line(
            name=cost.name,
            amount=cost.amount,
            currency_code=cur_code,
            base_currency_code=base_currency_code,
            base_amount=base_amount,
        )
        lines.append(f"• {esc(line_str)}")

    return "\n".join(lines)


async def save_costs_to_db(
    user_id: int, costs: list[Cost]
) -> tuple[bool, list[str]]:
    """Save costs to DB, resolving currencies from the catalogue.

    For each cost:
    - ``currency_code=None`` → use the base currency.
    - Known code → use the matching currency.
    - Unknown code → skip the cost and add to the ``unknown_lines`` list.

    Returns:
        A tuple of ``(success, unknown_lines)`` where *success* is ``True``
        unless a DB error occurred, and *unknown_lines* contains raw line
        descriptions for costs whose currency was not in the catalogue.
    """
    unknown_lines: list[str] = []
    valid_costs: list[tuple[Cost, Currency]] = []

    async with get_session() as session:
        base = await get_base_currency(session)
        catalogue: dict[str, Currency] = {str(c.code): c for c in await list_currencies(session)}

        for cost in costs:
            resolved: Currency | None
            if cost.currency_code is None:
                resolved = base
            else:
                resolved = catalogue.get(cost.currency_code)
                if resolved is None:
                    unknown_lines.append(
                        f"{cost.name} {cost.amount} [{cost.currency_code}] — неизвестная валюта"
                    )
                    continue
            if resolved is None:
                continue
            valid_costs.append((cost, resolved))

        if not valid_costs:
            # Nothing to save is OK; unknown_lines are reported back
            return True, unknown_lines

        try:
            for cost, currency in valid_costs:
                await save_message(
                    session=session,
                    user_id=user_id,
                    text=f"{cost.name} {cost.amount}",
                    amount=cost.amount,
                    currency_id=int(currency.id),
                )
            await session.commit()
            return True, unknown_lines
        except SQLAlchemyError:
            logger.exception("DB error while saving costs")
            await session.rollback()
            return False, unknown_lines


async def _compute_base_amounts(
    costs: list[Cost],
) -> tuple[str, dict[int, Decimal]]:
    """Compute base amounts for a list of costs using the rate cache.

    Returns ``(base_currency_code, {index: base_amount})``.
    """
    base_amounts: dict[int, Decimal] = {}
    base_currency_code = "RUB"

    async with get_session() as session:
        base = await get_base_currency(session)
        if base:
            base_currency_code = str(base.code)
        catalogue: dict[str, Currency] = {str(c.code): c for c in await list_currencies(session)}
        cache = RateCache(session)

        from datetime import date as _date
        today = _date.today()

        for idx, cost in enumerate(costs):
            cur_code = cost.currency_code or base_currency_code
            currency = catalogue.get(cur_code)
            if currency is None:
                base_amounts[idx] = cost.amount
            else:
                base_amounts[idx] = await cache.compute_base_amount(
                    cost.amount, currency, today
                )

    return base_currency_code, base_amounts


# =====================
# MESSAGE HANDLER
# =====================

@router.message(~Command(commands=["start", "help", "menu"]))
async def handle_message(message: Message, state: FSMContext):
    if not message.text or not message.from_user:
        return

    logger.debug(
        "Received message from user %s: %s",
        message.from_user.id,
        message.text[:50] + "..." if len(message.text) > 50 else message.text,
    )

    try:
        result = parse_message(message.text)
    except MessageMaxLinesCountExceed:
        await message.answer(MSG_MESSAGE_MAX_LINES_COUNT)
        return
    except MessageMaxLengthExceed:
        await message.answer(MSG_MESSAGE_MAX_LENGTH)
        return
    except MessageMaxLineLengthExceed as e:
        await message.answer(f"{MSG_MESSAGE_MAX_LINE_LENGTH} {str(e)[:30]}...")
        return

    if not result:
        await message.answer(MSG_PARSE_ERROR)
        await message.answer(HELP_TEXT)
        return

    # Есть нераспарсенные строки → подтверждение
    if result.invalid_lines:
        await state.set_state(SaveCostsStates.waiting_confirmation)
        await state.update_data(
            valid_costs=result.valid_lines,
            invalid_lines=result.invalid_lines,
        )

        base_currency_code, base_amounts = await _compute_base_amounts(result.valid_lines)

        await message.answer(
            format_confirmation_message(
                result.valid_lines,
                result.invalid_lines,
                base_currency_code=base_currency_code,
                base_amounts=base_amounts,
            ),
            reply_markup=build_confirmation_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    # Всё распарсилось → сохраняем сразу
    success, unknown_lines = await save_costs_to_db(message.from_user.id, result.valid_lines)

    # Merge unknown currency lines into invalid_lines for display
    all_invalid = list(result.invalid_lines) + unknown_lines

    if not success:
        await message.answer(MSG_DB_ERROR)
        return

    # If every valid line was rejected due to unknown currency → treat as parse error
    if unknown_lines and not (
        set(c.name for c in result.valid_lines) - {
            line.split(" ")[0] for line in unknown_lines
        }
    ):
        if all_invalid:
            await message.answer(
                format_confirmation_message(
                    [],
                    all_invalid,
                    base_currency_code="RUB",
                ),
                parse_mode=ParseMode.HTML,
            )
            return

    logger.debug("Saved costs for user %s", message.from_user.id)

    base_currency_code, base_amounts = await _compute_base_amounts(result.valid_lines)

    await message.answer(
        format_success_message(
            result.valid_lines,
            base_currency_code=base_currency_code,
            base_amounts=base_amounts,
        ),
        parse_mode=ParseMode.HTML,
    )


# =====================
# CALLBACKS
# =====================

@router.callback_query(F.data == CALLBACK_CONFIRM, SaveCostsStates.waiting_confirmation)
async def handle_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    valid_costs: list[Cost] = data.get("valid_costs", [])

    if not valid_costs:
        await callback.answer("Нет данных")
        await state.clear()
        return

    success, unknown_lines = await save_costs_to_db(callback.from_user.id, valid_costs)

    if not success:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(MSG_DB_ERROR)
        else:
            await callback.answer(MSG_DB_ERROR, show_alert=True)
        return

    await state.clear()

    base_currency_code, base_amounts = await _compute_base_amounts(valid_costs)
    success_text = format_success_message(
        valid_costs,
        base_currency_code=base_currency_code,
        base_amounts=base_amounts,
    )

    if isinstance(callback.message, Message):
        await callback.message.edit_text(success_text)
    else:
        await callback.answer(success_text)


@router.callback_query(F.data == CALLBACK_CANCEL, SaveCostsStates.waiting_confirmation)
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ Галя, отмена! Исправьте строки и отправьте сообщение снова."
        )
    else:
        await callback.answer("❌ Галя, отмена! Исправьте строки и отправьте сообщение снова.")
