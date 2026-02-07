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
    count_admins,
    create_user,
    delete_user,
    get_all_users,
    get_user_by_id,
    update_user,
    update_user_password,
)
from bot.security import hash_password
from bot.web.auth import (
    get_csrf_token,
    get_current_user_name,
    get_flash_message,
    is_admin,
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

# Valid role values
VALID_ROLES = ("admin", "user")


def _get_auth_context(request: Request) -> dict:
    """Get common auth context for templates."""
    return {
        "authenticated": True,
        "user_name": get_current_user_name(request),
        "is_admin": is_admin(request),
    }


def _require_admin(request: Request) -> RedirectResponse | None:
    """Check if user is admin, return redirect if not."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)
    if not is_admin(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
    return None


def _render_form_error(request: Request, error: str, user, form_data: dict | None) -> HTMLResponse:
    """Helper to render user form with error."""
    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            **_get_auth_context(request),
            "user": user,
            "error": error,
            "form_data": form_data,
            "csrf_token": get_csrf_token(request),
            "valid_roles": VALID_ROLES,
        },
    )


@router.get("", response_class=HTMLResponse)
async def users_list(request: Request):
    """Show list of all users. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    flash_message, flash_type = get_flash_message(request)

    async with get_db_session() as session:
        users = await get_all_users(session)

    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            **_get_auth_context(request),
            "users": users,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "csrf_token": get_csrf_token(request),
            "valid_roles": VALID_ROLES,
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def add_user_form(request: Request):
    """Show add user form. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            **_get_auth_context(request),
            "user": None,
            "csrf_token": get_csrf_token(request),
            "valid_roles": VALID_ROLES,
        },
    )


@router.post("/add")
async def add_user(
    request: Request,
    name: str = Form(...),
    telegram_id: str = Form(...),
    role: str = Form("user"),
    password: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle add user form submission. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {"name": name, "telegram_id": telegram_id, "role": role}

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

    # Validate role
    if role not in VALID_ROLES:
        return _render_form_error(request, "Некорректная роль", None, form_data)

    # Validate password
    if len(password) < 4:
        return _render_form_error(request, "Пароль должен быть не менее 4 символов", None, form_data)

    async with get_db_session() as session:
        try:
            hashed = hash_password(password)
            user = await create_user(session, telegram_id=telegram_id_int, name=name.strip(), password_hash=hashed)
            user.role = role  # type: ignore[assignment]
            await session.commit()
            logger.info("Added user telegram_id=%d, name=%s, role=%s", telegram_id_int, name, role)
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
    """Show edit user form. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    async with get_db_session() as session:
        user = await get_user_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            **_get_auth_context(request),
            "user": user,
            "csrf_token": get_csrf_token(request),
            "valid_roles": VALID_ROLES,
        },
    )


@router.post("/{user_id}/edit")
async def edit_user(
    request: Request,
    user_id: int,
    name: str = Form(...),
    telegram_id: str = Form(...),
    role: str = Form("user"),
    new_password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Handle edit user form submission. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {"name": name, "telegram_id": telegram_id, "role": role}

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

    # Validate role
    if role not in VALID_ROLES:
        return _render_form_error(request, "Некорректная роль", existing_user, form_data)

    # Validate password if provided
    if new_password and len(new_password) < 4:
        return _render_form_error(request, "Пароль должен быть не менее 4 символов", existing_user, form_data)

    async with get_db_session() as session:
        try:
            # Check last admin protection before demotion
            if existing_user and existing_user.role == "admin" and role != "admin":
                admin_count = await count_admins(session)
                if admin_count <= 1:
                    return _render_form_error(
                        request, "Нельзя снять роль администратора у единственного администратора", existing_user, form_data
                    )

            updated = await update_user(
                session, user_id, telegram_id=telegram_id_int, name=name.strip(), role=role
            )
            if not updated:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            # Update password if provided
            if new_password:
                await update_user_password(session, user_id, hash_password(new_password))

            await session.commit()
            logger.info("Updated user #%d: telegram_id=%d, name=%s, role=%s", user_id, telegram_id_int, name, role)
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
    """Handle delete user. Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    async with get_db_session() as session:
        try:
            # Check if this is the last admin
            user_to_delete = await get_user_by_id(session, user_id)
            if not user_to_delete:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            if user_to_delete.role == "admin":
                admin_count = await count_admins(session)
                if admin_count <= 1:
                    set_flash_message(request, "Нельзя удалить единственного администратора", "error")
                    return RedirectResponse(url=f"{settings.web_root_path}/users", status_code=303)

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
