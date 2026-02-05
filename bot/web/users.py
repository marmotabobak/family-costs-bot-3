"""Web UI for users management."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError

from bot.config import settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.users import (
    create_user,
    delete_user,
    get_all_users,
    get_user_by_id,
    update_user,
)
from bot.web.auth import (
    get_csrf_token,
    get_flash_message,
    is_authenticated,
    set_flash_message,
    validate_csrf_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path


def _render_form_error(request: Request, error: str, user, form_data: dict | None) -> HTMLResponse:
    """Helper to render user form with error."""
    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": user,
            "error": error,
            "form_data": form_data,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.get("", response_class=HTMLResponse)
async def users_list(request: Request):
    """Show list of all users."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    flash_message, flash_type = get_flash_message(request)

    async with get_db_session() as session:
        users = await get_all_users(session)

    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            "users": users,
            "authenticated": True,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def add_user_form(request: Request):
    """Show add user form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": None,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/add")
async def add_user(
    request: Request,
    name: str = Form(...),
    telegram_id: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle add user form submission."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {"name": name, "telegram_id": telegram_id}

    # Validate name
    if not name.strip():
        return _render_form_error(request, "Имя не может быть пустым", None, form_data)

    # Validate telegram_id
    try:
        telegram_id_int = int(telegram_id)
    except ValueError:
        return _render_form_error(request, "Telegram ID должен быть числом", None, form_data)

    if telegram_id_int < 1:
        return _render_form_error(request, "Telegram ID должен быть больше 0", None, form_data)

    async with get_db_session() as session:
        try:
            await create_user(session, telegram_id=telegram_id_int, name=name.strip())
            await session.commit()
            logger.info("Added user telegram_id=%d, name=%s", telegram_id_int, name)
        except IntegrityError:
            await session.rollback()
            return _render_form_error(
                request, "Пользователь с таким Telegram ID уже существует", None, form_data
            )
        except Exception as e:
            logger.exception("Error adding user: %s", e)
            await session.rollback()
            return _render_form_error(request, "Ошибка сохранения в базу данных", None, form_data)

    set_flash_message(request, "Пользователь успешно добавлен", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/users", status_code=303)


@router.get("/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(request: Request, user_id: int):
    """Show edit user form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    async with get_db_session() as session:
        user = await get_user_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": user,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/{user_id}/edit")
async def edit_user(
    request: Request,
    user_id: int,
    name: str = Form(...),
    telegram_id: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle edit user form submission."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {"name": name, "telegram_id": telegram_id}

    # Fetch existing user for error re-renders (keeps form action correct)
    async with get_db_session() as session:
        existing_user = await get_user_by_id(session, user_id)

    # Validate name
    if not name.strip():
        return _render_form_error(request, "Имя не может быть пустым", existing_user, form_data)

    # Validate telegram_id
    try:
        telegram_id_int = int(telegram_id)
    except ValueError:
        return _render_form_error(request, "Telegram ID должен быть числом", existing_user, form_data)

    if telegram_id_int < 1:
        return _render_form_error(request, "Telegram ID должен быть больше 0", existing_user, form_data)

    async with get_db_session() as session:
        try:
            updated = await update_user(session, user_id, telegram_id=telegram_id_int, name=name.strip())
            if not updated:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            await session.commit()
            logger.info("Updated user #%d: telegram_id=%d, name=%s", user_id, telegram_id_int, name)
        except IntegrityError:
            await session.rollback()
            return _render_form_error(
                request, "Пользователь с таким Telegram ID уже существует", existing_user, form_data
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error updating user: %s", e)
            await session.rollback()
            return _render_form_error(request, "Ошибка сохранения в базу данных", existing_user, form_data)

    set_flash_message(request, "Пользователь успешно обновлён", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/users", status_code=303)


@router.post("/{user_id}/delete")
async def delete_user_route(
    request: Request,
    user_id: int,
    csrf_token: str = Form(""),
):
    """Handle delete user."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    async with get_db_session() as session:
        try:
            deleted = await delete_user(session, user_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            await session.commit()
            logger.info("Deleted user #%d", user_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error deleting user: %s", e)
            await session.rollback()
            set_flash_message(request, "Ошибка удаления", "error")
            return RedirectResponse(url=f"{settings.web_root_path}/users", status_code=303)

    set_flash_message(request, "Пользователь успешно удалён", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/users", status_code=303)
