"""Web UI router for currency configuration (admin-only).

All routes require admin access via the ``admin_required`` FastAPI dependency.

Route map:
- ``GET  /config``                            → redirect to ``/config/currencies``
- ``GET  /config/currencies``                 → list currencies + create form
- ``POST /config/currencies``                 → create a currency
- ``POST /config/currencies/{id}/promote``    → promote to base
- ``GET  /config/currencies/{id}/edit``       → edit form (default_rate only)
- ``POST /config/currencies/{id}/edit``       → update default_rate
- ``POST /config/currencies/{id}/delete``     → delete currency
- ``GET  /config/currencies/{id}/rates``      → list dated rates + add form
- ``POST /config/currencies/{id}/rates``      → add a dated rate
- ``POST /config/currencies/{id}/rates/{rate_id}/delete`` → delete dated rate
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.currencies import (
    create_currency,
    create_exchange_rate,
    delete_currency,
    delete_exchange_rate,
    get_currency_by_id,
    list_currencies,
    list_exchange_rates,
    promote_to_base,
    update_currency,
)
from bot.utils import format_amount
from bot.web.auth import (
    admin_required,
    get_csrf_token,
    get_current_user_name,
    get_flash_message,
    is_admin,
    set_flash_message,
    validate_csrf_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(admin_required)],
)

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path
templates.env.filters["format_amount"] = format_amount


def _auth_context(request: Request) -> dict:
    """Common template context for authenticated admin pages."""
    return {
        "authenticated": True,
        "user_name": get_current_user_name(request),
        "is_admin": is_admin(request),
    }


# ---------------------------------------------------------------------------
# /config
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def config_index(request: Request):
    """Redirect to currencies list."""
    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies", status_code=303
    )


# ---------------------------------------------------------------------------
# /config/currencies
# ---------------------------------------------------------------------------

@router.get("/currencies", response_class=HTMLResponse)
async def currencies_list(request: Request):
    """Show currency list and create form."""
    async with get_db_session() as session:
        currencies = await list_currencies(session)

    flash_message, flash_type = get_flash_message(request)

    return templates.TemplateResponse(
        request,
        "config/currencies.html",
        {
            **_auth_context(request),
            "currencies": currencies,
            "csrf_token": get_csrf_token(request),
            "flash_message": flash_message,
            "flash_type": flash_type,
            "error": None,
        },
    )


@router.post("/currencies", response_class=HTMLResponse)
async def currencies_create(
    request: Request,
    code: str = Form(...),
    default_rate: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle currency create form submission."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    async with get_db_session() as session:
        currencies = await list_currencies(session)

    try:
        rate_decimal = Decimal(default_rate.replace(",", "."))
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            request,
            "config/currencies.html",
            {
                **_auth_context(request),
                "currencies": currencies,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": "Некорректный курс валюты",
            },
        )

    try:
        async with get_db_session() as session:
            await create_currency(session, code.strip().upper(), rate_decimal)
            await session.commit()
        set_flash_message(request, f"Валюта {code.upper()} добавлена", "success")
    except ValueError as e:
        async with get_db_session() as session:
            currencies = await list_currencies(session)
        return templates.TemplateResponse(
            request,
            "config/currencies.html",
            {
                **_auth_context(request),
                "currencies": currencies,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": str(e),
            },
        )
    except Exception as e:
        logger.exception("Error creating currency: %s", e)
        set_flash_message(request, "Ошибка при добавлении валюты", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies", status_code=303
    )


@router.post("/currencies/{currency_id}/promote", response_class=HTMLResponse)
async def currencies_promote(
    request: Request,
    currency_id: int,
    csrf_token: str = Form(""),
):
    """Promote a currency to base."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        async with get_db_session() as session:
            currency = await promote_to_base(session, currency_id)
            await session.commit()
        set_flash_message(
            request, f"Валюта {currency.code} стала базовой", "success"
        )
    except ValueError as e:
        set_flash_message(request, str(e), "error")
    except Exception as e:
        logger.exception("Error promoting currency %d: %s", currency_id, e)
        set_flash_message(request, "Ошибка при изменении базовой валюты", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies", status_code=303
    )


@router.get("/currencies/{currency_id}/edit", response_class=HTMLResponse)
async def currencies_edit_form(request: Request, currency_id: int):
    """Show edit form for a non-base currency's default_rate."""
    async with get_db_session() as session:
        currency = await get_currency_by_id(session, currency_id)

    if currency is None:
        raise HTTPException(status_code=404, detail="Валюта не найдена")

    return templates.TemplateResponse(
        request,
        "config/currencies.html",
        {
            **_auth_context(request),
            "currencies": [],
            "edit_currency": currency,
            "csrf_token": get_csrf_token(request),
            "flash_message": None,
            "flash_type": None,
            "error": None,
        },
    )


@router.post("/currencies/{currency_id}/edit", response_class=HTMLResponse)
async def currencies_edit(
    request: Request,
    currency_id: int,
    default_rate: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle edit form submission for default_rate."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        rate_decimal = Decimal(default_rate.replace(",", "."))
    except (InvalidOperation, ValueError):
        async with get_db_session() as session:
            currency = await get_currency_by_id(session, currency_id)
        return templates.TemplateResponse(
            request,
            "config/currencies.html",
            {
                **_auth_context(request),
                "currencies": [],
                "edit_currency": currency,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": "Некорректный курс валюты",
            },
        )

    try:
        async with get_db_session() as session:
            currency = await update_currency(session, currency_id, rate_decimal)
            await session.commit()
        if currency:
            set_flash_message(
                request, f"Курс валюты {currency.code} обновлён", "success"
            )
    except ValueError as e:
        async with get_db_session() as session:
            currency = await get_currency_by_id(session, currency_id)
        return templates.TemplateResponse(
            request,
            "config/currencies.html",
            {
                **_auth_context(request),
                "currencies": [],
                "edit_currency": currency,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": str(e),
            },
        )
    except Exception as e:
        logger.exception("Error updating currency %d: %s", currency_id, e)
        set_flash_message(request, "Ошибка при обновлении курса", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies", status_code=303
    )


@router.post("/currencies/{currency_id}/delete", response_class=HTMLResponse)
async def currencies_delete(
    request: Request,
    currency_id: int,
    csrf_token: str = Form(""),
):
    """Delete a currency."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        async with get_db_session() as session:
            deleted = await delete_currency(session, currency_id)
            await session.commit()
        if deleted:
            set_flash_message(request, "Валюта удалена", "success")
        else:
            set_flash_message(request, "Валюта не найдена", "error")
    except ValueError as e:
        # Re-render the list with the error message
        async with get_db_session() as session:
            currencies = await list_currencies(session)
        flash_message, flash_type = get_flash_message(request)
        return templates.TemplateResponse(
            request,
            "config/currencies.html",
            {
                **_auth_context(request),
                "currencies": currencies,
                "csrf_token": get_csrf_token(request),
                "flash_message": flash_message,
                "flash_type": flash_type,
                "error": str(e),
            },
        )
    except Exception as e:
        logger.exception("Error deleting currency %d: %s", currency_id, e)
        set_flash_message(request, "Ошибка при удалении валюты", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies", status_code=303
    )


# ---------------------------------------------------------------------------
# /config/currencies/{id}/rates
# ---------------------------------------------------------------------------

@router.get("/currencies/{currency_id}/rates", response_class=HTMLResponse)
async def rates_list(request: Request, currency_id: int):
    """Show dated rates list and add form for a currency."""
    async with get_db_session() as session:
        currency = await get_currency_by_id(session, currency_id)
        if currency is None:
            raise HTTPException(status_code=404, detail="Валюта не найдена")
        rates = await list_exchange_rates(session, currency_id)

    flash_message, flash_type = get_flash_message(request)

    return templates.TemplateResponse(
        request,
        "config/rates.html",
        {
            **_auth_context(request),
            "currency": currency,
            "rates": rates,
            "csrf_token": get_csrf_token(request),
            "flash_message": flash_message,
            "flash_type": flash_type,
            "error": None,
        },
    )


@router.post("/currencies/{currency_id}/rates", response_class=HTMLResponse)
async def rates_create(
    request: Request,
    currency_id: int,
    rate: str = Form(...),
    rate_date: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle add-rate form submission."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    async with get_db_session() as session:
        currency = await get_currency_by_id(session, currency_id)
        if currency is None:
            raise HTTPException(status_code=404, detail="Валюта не найдена")
        rates = await list_exchange_rates(session, currency_id)

    try:
        rate_decimal = Decimal(rate.replace(",", "."))
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            request,
            "config/rates.html",
            {
                **_auth_context(request),
                "currency": currency,
                "rates": rates,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": "Некорректный курс",
            },
        )

    try:
        parsed_date = date.fromisoformat(rate_date)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "config/rates.html",
            {
                **_auth_context(request),
                "currency": currency,
                "rates": rates,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": "Некорректная дата",
            },
        )

    try:
        async with get_db_session() as session:
            await create_exchange_rate(session, currency_id, rate_decimal, parsed_date)
            await session.commit()
        set_flash_message(request, "Курс добавлен", "success")
    except ValueError as e:
        async with get_db_session() as session:
            currency = await get_currency_by_id(session, currency_id)
            rates = await list_exchange_rates(session, currency_id)
        return templates.TemplateResponse(
            request,
            "config/rates.html",
            {
                **_auth_context(request),
                "currency": currency,
                "rates": rates,
                "csrf_token": get_csrf_token(request),
                "flash_message": None,
                "flash_type": None,
                "error": str(e),
            },
        )
    except Exception as e:
        logger.exception(
            "Error creating exchange rate for currency %d: %s", currency_id, e
        )
        set_flash_message(request, "Ошибка при добавлении курса", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies/{currency_id}/rates",
        status_code=303,
    )


@router.post(
    "/currencies/{currency_id}/rates/{rate_id}/delete",
    response_class=HTMLResponse,
)
async def rates_delete(
    request: Request,
    currency_id: int,
    rate_id: int,
    csrf_token: str = Form(""),
):
    """Delete a dated exchange rate."""
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        async with get_db_session() as session:
            deleted = await delete_exchange_rate(session, rate_id)
            await session.commit()
        if deleted:
            set_flash_message(request, "Курс удалён", "success")
        else:
            set_flash_message(request, "Курс не найден", "error")
    except Exception as e:
        logger.exception("Error deleting rate %d: %s", rate_id, e)
        set_flash_message(request, "Ошибка при удалении курса", "error")

    return RedirectResponse(
        url=f"{settings.web_root_path}/config/currencies/{currency_id}/rates",
        status_code=303,
    )
