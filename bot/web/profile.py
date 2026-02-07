"""Web UI for user profile operations (change password)."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.users import get_user_by_id, update_user_password
from bot.security import hash_password, verify_password
from bot.web.auth import (
    get_csrf_token,
    get_current_user_id,
    get_current_user_name,
    is_admin,
    is_authenticated,
    set_flash_message,
    validate_csrf_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path


def _get_auth_context(request: Request) -> dict:
    """Get common auth context for templates."""
    return {
        "authenticated": True,
        "user_name": get_current_user_name(request),
        "is_admin": is_admin(request),
    }


def _require_authenticated(request: Request) -> RedirectResponse | None:
    """Check if user is authenticated, return redirect if not."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)
    return None


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_form(request: Request):
    """Show change password form. Available to all authenticated users."""
    redirect = _require_authenticated(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        request,
        "profile/change_password.html",
        {
            **_get_auth_context(request),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(""),
):
    """Handle change password form submission. Available to all authenticated users."""
    redirect = _require_authenticated(request)
    if redirect:
        return redirect

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    # Get current user ID from session
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    # Validate passwords match
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "profile/change_password.html",
            {
                **_get_auth_context(request),
                "error": "Новый пароль и подтверждение не совпадают",
                "csrf_token": get_csrf_token(request),
            },
        )

    # Validate password length
    if len(new_password) < 4:
        return templates.TemplateResponse(
            request,
            "profile/change_password.html",
            {
                **_get_auth_context(request),
                "error": "Пароль должен быть не менее 4 символов",
                "csrf_token": get_csrf_token(request),
            },
        )

    # Verify current password and update
    async with get_db_session() as session:
        user = await get_user_by_id(session, user_id)
        if not user:
            return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

        # Verify current password
        if not user.password_hash or not verify_password(current_password, str(user.password_hash)):
            return templates.TemplateResponse(
                request,
                "profile/change_password.html",
                {
                    **_get_auth_context(request),
                    "error": "Текущий пароль неверен",
                    "csrf_token": get_csrf_token(request),
                },
            )

        # Update password
        try:
            hashed = hash_password(new_password)
            await update_user_password(session, user_id, hashed)
            await session.commit()
            logger.info("User #%d changed password", user_id)
        except Exception as e:
            logger.exception("Error changing password: %s", e)
            await session.rollback()
            return templates.TemplateResponse(
                request,
                "profile/change_password.html",
                {
                    **_get_auth_context(request),
                    "error": "Ошибка сохранения пароля",
                    "csrf_token": get_csrf_token(request),
                },
            )

    set_flash_message(request, "Пароль успешно изменён", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
