"""Web UI for managing costs (CRUD operations)."""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.messages import (
    bulk_delete_messages,
    bulk_update_messages_date,
    delete_message_by_id,
    get_all_costs_paginated,
    get_all_messages,
    get_message_by_id,
    save_message,
    update_message,
)
from bot.db.repositories.users import get_all_users
from bot.utils import format_amount, pluralize
from bot.web.auth import (
    get_csrf_token,
    get_flash_message,
    is_authenticated,
    set_flash_message,
    validate_csrf_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costs", tags=["costs"])

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path
templates.env.filters["format_amount"] = format_amount

# Fields sortable at the DB level; name/amount require Python-side sorting
_DB_SORT_FIELDS = {"id", "created_at", "user_id"}


@dataclass
class ParsedCost:
    """Parsed cost data from Message."""

    id: int
    name: str
    amount: Decimal
    user_id: int
    created_at: datetime


@dataclass
class CostsResponse:
    """Paginated costs response for templates."""

    items: list
    total: int
    page: int
    per_page: int
    total_pages: int


def parse_message_to_cost(message) -> ParsedCost:
    """Parse Message object to ParsedCost with name and amount extracted."""
    parts = message.text.rsplit(maxsplit=1)
    if len(parts) == 2:
        try:
            amount = Decimal(parts[1].replace(",", "."))
            name = parts[0]
        except (InvalidOperation, ValueError):
            name = message.text
            amount = Decimal("0")
    else:
        name = message.text
        amount = Decimal("0")

    return ParsedCost(
        id=message.id,
        name=name,
        amount=amount,
        user_id=message.user_id,
        created_at=message.created_at,
    )


async def _get_users_for_form():
    """Fetch users list for form dropdowns."""
    async with get_db_session() as session:
        return await get_all_users(session)


def render_form_error(
    request: Request,
    error: str,
    cost: ParsedCost | None,
    form_data: dict,
    users: list,
) -> HTMLResponse:
    """Helper to render form with error."""
    return templates.TemplateResponse(
        request,
        "costs/form.html",
        {
            "error": error,
            "cost": cost,
            "authenticated": True,
            "form_data": form_data,
            "csrf_token": get_csrf_token(request),
            "users": users,
        },
    )


# --- CRUD routes ---


@router.get("", response_class=HTMLResponse)
async def costs_list(
    request: Request,
    page: int = 1,
    per_page: int = 100,
    order_by: str = "created_at",
    order_dir: str = "desc",
):
    """Show paginated list of all costs."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if page < 1:
        page = 1
    if per_page not in (20, 50, 100, 200):
        per_page = 100
    if order_dir not in ("asc", "desc"):
        order_dir = "desc"
    if order_by not in ("id", "created_at", "user_id", "name", "amount"):
        order_by = "created_at"

    flash_message, flash_type = get_flash_message(request)

    async with get_db_session() as session:
        users = await get_all_users(session)

        if order_by in _DB_SORT_FIELDS:
            paginated = await get_all_costs_paginated(
                session,
                page=page,
                per_page=per_page,
                order_by=order_by,
                order_dir=order_dir,
            )
            items = [parse_message_to_cost(msg) for msg in paginated.items]
            costs = CostsResponse(
                items=items,
                total=paginated.total,
                page=paginated.page,
                per_page=paginated.per_page,
                total_pages=paginated.total_pages,
            )
        else:
            # name / amount: fetch all, sort in Python, paginate in Python
            all_messages = await get_all_messages(session)
            all_items = [parse_message_to_cost(msg) for msg in all_messages]
            reverse = order_dir == "desc"
            if order_by == "name":
                all_items.sort(key=lambda c: c.name.lower(), reverse=reverse)
            else:  # amount
                all_items.sort(key=lambda c: c.amount, reverse=reverse)

            total = len(all_items)
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            items = all_items[start : start + per_page]
            costs = CostsResponse(
                items=items,
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
            )

    users_map = {u.telegram_id: u.name for u in users}

    return templates.TemplateResponse(
        request,
        "costs/list.html",
        {
            "costs": costs,
            "users_map": users_map,
            "authenticated": True,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "csrf_token": get_csrf_token(request),
            "order_by": order_by,
            "order_dir": order_dir,
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def add_cost_form(request: Request):
    """Show add cost form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    users = await _get_users_for_form()

    return templates.TemplateResponse(
        request,
        "costs/form.html",
        {
            "cost": None,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
            "users": users,
        },
    )


@router.post("/add")
async def add_cost(
    request: Request,
    name: str = Form(...),
    amount: str = Form(...),
    user_id: int = Form(...),
    created_at: str = Form(""),
    csrf_token: str = Form(""),
):
    """Handle add cost form submission."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "created_at": created_at,
    }
    users = await _get_users_for_form()

    # Validate amount
    try:
        amount_decimal = Decimal(amount.replace(",", "."))
    except (InvalidOperation, ValueError):
        return render_form_error(request, "Некорректная сумма", None, form_data, users)

    # Validate user_id
    if user_id < 1:
        return render_form_error(request, "User ID должен быть больше 0", None, form_data, users)

    # Parse datetime
    parsed_created_at = None
    if created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at)
        except ValueError:
            return render_form_error(request, "Некорректная дата", None, form_data, users)

    text = f"{name} {amount_decimal}"

    async with get_db_session() as session:
        try:
            await save_message(
                session=session,
                user_id=user_id,
                text=text,
                created_at=parsed_created_at,
            )
            await session.commit()
            logger.info("Added new cost via web: %s", text)
        except Exception as e:
            logger.exception("Error adding cost: %s", e)
            await session.rollback()
            return render_form_error(
                request, "Ошибка сохранения в базу данных", None, form_data, users
            )

    set_flash_message(request, "Расход успешно добавлен", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)


@router.get("/{cost_id}/edit", response_class=HTMLResponse)
async def edit_cost_form(request: Request, cost_id: int):
    """Show edit cost form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    async with get_db_session() as session:
        message = await get_message_by_id(session, cost_id)
        if not message:
            raise HTTPException(status_code=404, detail="Расход не найден")

        cost = parse_message_to_cost(message)
        users = await get_all_users(session)

    return templates.TemplateResponse(
        request,
        "costs/form.html",
        {
            "cost": cost,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
            "users": users,
        },
    )


@router.post("/{cost_id}/edit")
async def edit_cost(
    request: Request,
    cost_id: int,
    name: str = Form(...),
    amount: str = Form(...),
    user_id: int = Form(...),
    created_at: str = Form(""),
    csrf_token: str = Form(""),
):
    """Handle edit cost form submission."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "created_at": created_at,
    }

    async with get_db_session() as session:
        users = await get_all_users(session)
        existing_message = await get_message_by_id(session, cost_id)
    existing_cost = parse_message_to_cost(existing_message) if existing_message else None

    # Validate amount
    try:
        amount_decimal = Decimal(amount.replace(",", "."))
    except (InvalidOperation, ValueError):
        return render_form_error(request, "Некорректная сумма", existing_cost, form_data, users)

    # Validate user_id
    if user_id < 1:
        return render_form_error(request, "User ID должен быть больше 0", existing_cost, form_data, users)

    # Parse datetime
    parsed_created_at = None
    if created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at)
        except ValueError:
            return render_form_error(request, "Некорректная дата", existing_cost, form_data, users)

    text = f"{name} {amount_decimal}"

    async with get_db_session() as session:
        try:
            message = await update_message(
                session=session,
                message_id=cost_id,
                text=text,
                user_id=user_id,
                created_at=parsed_created_at,
            )
            if not message:
                raise HTTPException(status_code=404, detail="Расход не найден")
            await session.commit()
            logger.info("Updated cost #%d via web: %s", cost_id, text)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error updating cost: %s", e)
            await session.rollback()
            return render_form_error(
                request, "Ошибка сохранения в базу данных", existing_cost, form_data, users
            )

    set_flash_message(request, "Расход успешно обновлён", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)


@router.post("/{cost_id}/delete")
async def delete_cost(
    request: Request,
    cost_id: int,
    csrf_token: str = Form(""),
):
    """Handle delete cost."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    async with get_db_session() as session:
        try:
            deleted = await delete_message_by_id(session, cost_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Расход не найден")
            await session.commit()
            logger.info("Deleted cost #%d via web", cost_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error deleting cost: %s", e)
            await session.rollback()
            set_flash_message(request, "Ошибка удаления", "error")
            return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    set_flash_message(request, "Расход успешно удалён", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)


@router.post("/bulk-delete")
async def bulk_delete(
    request: Request,
    ids: list[int] = Form(...),
    csrf_token: str = Form(""),
):
    """Handle bulk delete of selected costs."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if not ids:
        set_flash_message(request, "Не выбрано ничего", "error")
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    async with get_db_session() as session:
        try:
            count = await bulk_delete_messages(session, ids)
            await session.commit()
            logger.info("Bulk deleted %d costs via web", count)
        except Exception as e:
            logger.exception("Error in bulk delete: %s", e)
            await session.rollback()
            set_flash_message(request, "Ошибка удаления", "error")
            return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    set_flash_message(
        request,
        f"Удалено {count} {pluralize(count, 'расход', 'расхода', 'расходов')}",
        "success",
    )
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)


@router.post("/bulk-change-date")
async def bulk_change_date(
    request: Request,
    ids: list[int] = Form(...),
    new_date: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle bulk date change for selected costs."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if not ids:
        set_flash_message(request, "Не выбрано ничего", "error")
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    try:
        parsed_date = datetime.fromisoformat(new_date)
    except ValueError:
        set_flash_message(request, "Некорректная дата", "error")
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    async with get_db_session() as session:
        try:
            count = await bulk_update_messages_date(session, ids, parsed_date)
            await session.commit()
            logger.info("Bulk updated date for %d costs via web", count)
        except Exception as e:
            logger.exception("Error in bulk change date: %s", e)
            await session.rollback()
            set_flash_message(request, "Ошибка обновления даты", "error")
            return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    set_flash_message(
        request,
        f"Дата обновлена для {count} {pluralize(count, 'расхода', 'расходов', 'расходов')}",
        "success",
    )
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
