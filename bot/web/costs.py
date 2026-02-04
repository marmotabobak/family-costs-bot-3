"""Web UI for managing costs (CRUD operations)."""

import logging
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import Environment, settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.messages import (
    delete_message_by_id,
    get_all_costs_paginated,
    get_message_by_id,
    save_message,
    update_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costs", tags=["costs"])

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path

# In-memory session storage (in production use Redis or DB)
auth_sessions: dict[str, dict] = {}

# Session cookie name
SESSION_COOKIE = "costs_session"

# Session lifetime in seconds (24 hours)
SESSION_LIFETIME = 86400

# Rate limiting: track login attempts per IP
login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_urlsafe(32)


def cleanup_expired_sessions() -> None:
    """Remove expired sessions from memory."""
    now = datetime.now()
    expired_tokens = [
        token
        for token, session in auth_sessions.items()
        if (now - session.get("created_at", now)) > timedelta(seconds=SESSION_LIFETIME)
    ]
    for token in expired_tokens:
        del auth_sessions[token]


def get_session_from_cookie(request: Request) -> dict | None:
    """Get session data from cookie, checking expiration."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or token not in auth_sessions:
        return None

    session = auth_sessions[token]

    # Check session expiration
    created_at = session.get("created_at")
    if created_at and (datetime.now() - created_at) > timedelta(seconds=SESSION_LIFETIME):
        # Session expired, clean it up
        del auth_sessions[token]
        return None

    return session


def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated."""
    session = get_session_from_cookie(request)
    return session is not None and session.get("authenticated", False)


def get_csrf_token(request: Request) -> str | None:
    """Get CSRF token from session."""
    session = get_session_from_cookie(request)
    if session:
        return session.get("csrf_token")
    return None


def validate_csrf_token(request: Request, token: str) -> bool:
    """Validate CSRF token."""
    expected = get_csrf_token(request)
    if not expected or not token:
        return False
    return secrets.compare_digest(expected, token)


def check_rate_limit(client_ip: str) -> bool:
    """Check if IP has exceeded login rate limit. Returns True if allowed."""
    now = time.time()
    # Clean old attempts
    login_attempts[client_ip] = [
        t for t in login_attempts[client_ip] if now - t < LOGIN_WINDOW_SECONDS
    ]
    return len(login_attempts[client_ip]) < MAX_LOGIN_ATTEMPTS


def record_login_attempt(client_ip: str) -> None:
    """Record a login attempt for rate limiting."""
    login_attempts[client_ip].append(time.time())


def cleanup_old_rate_limits() -> None:
    """Remove old IPs from rate limiting dict."""
    now = time.time()
    old_ips = [
        ip
        for ip, attempts in login_attempts.items()
        if not attempts or all(now - t >= LOGIN_WINDOW_SECONDS for t in attempts)
    ]
    for ip in old_ips:
        del login_attempts[ip]


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


def get_flash_message(request: Request) -> tuple[str | None, str | None]:
    """Get flash message from session and clear it."""
    session = get_session_from_cookie(request)
    if session:
        message = session.pop("flash_message", None)
        msg_type = session.pop("flash_type", "info")
        return message, msg_type
    return None, None


def set_flash_message(request: Request, message: str, msg_type: str = "info") -> None:
    """Set flash message in session."""
    session = get_session_from_cookie(request)
    if session:
        session["flash_message"] = message
        session["flash_type"] = msg_type


async def get_cost_for_error_response(cost_id: int) -> ParsedCost | None:
    """Helper to fetch cost for error response rendering."""
    async with get_db_session() as session:
        message = await get_message_by_id(session, cost_id)
        return parse_message_to_cost(message) if message else None


def render_form_error(
    request: Request,
    error: str,
    cost: ParsedCost | None,
    form_data: dict,
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
        },
    )


# --- Authentication routes ---


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login form."""
    # Cleanup expired sessions and old rate limit entries periodically
    cleanup_expired_sessions()
    cleanup_old_rate_limits()

    if is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    return templates.TemplateResponse(
        request, "costs/login.html", {"authenticated": False}
    )


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    """Handle login form submission."""
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    if not check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {
                "error": "Слишком много попыток входа. Повторите через 5 минут.",
                "authenticated": False,
            },
        )

    if not settings.web_password:
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {
                "error": "Пароль не настроен. Установите WEB_PASSWORD в переменных окружения.",
                "authenticated": False,
            },
        )

    # Use timing-safe comparison to prevent timing attacks
    password_matches = secrets.compare_digest(
        password.encode("utf-8"), settings.web_password.encode("utf-8")
    )

    if not password_matches:
        record_login_attempt(client_ip)
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {"error": "Неверный пароль", "authenticated": False},
        )

    # Create session with CSRF token
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    auth_sessions[token] = {
        "authenticated": True,
        "created_at": datetime.now(),
        "csrf_token": csrf_token,
    }

    response = RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_LIFETIME,
        secure=settings.env == Environment.prod,  # Secure in production
    )
    logger.info("User logged in to costs management")
    return response


@router.get("/logout")
async def logout(request: Request):
    """Handle logout."""
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in auth_sessions:
        del auth_sessions[token]

    response = RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE)
    return response


# --- CRUD routes ---


@router.get("", response_class=HTMLResponse)
async def costs_list(request: Request, page: int = 1):
    """Show paginated list of all costs."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    # Validate page parameter
    if page < 1:
        page = 1

    flash_message, flash_type = get_flash_message(request)

    async with get_db_session() as session:
        paginated = await get_all_costs_paginated(session, page=page, per_page=20)

        items = [parse_message_to_cost(msg) for msg in paginated.items]

        costs = CostsResponse(
            items=items,
            total=paginated.total,
            page=paginated.page,
            per_page=paginated.per_page,
            total_pages=paginated.total_pages,
        )

    return templates.TemplateResponse(
        request,
        "costs/list.html",
        {
            "costs": costs,
            "authenticated": True,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def add_cost_form(request: Request):
    """Show add cost form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "costs/form.html",
        {
            "cost": None,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
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
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    # Validate CSRF token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "created_at": created_at,
    }

    # Validate amount
    try:
        amount_decimal = Decimal(amount.replace(",", "."))
    except (InvalidOperation, ValueError):
        return render_form_error(request, "Некорректная сумма", None, form_data)

    # Validate user_id
    if user_id < 1:
        return render_form_error(request, "User ID должен быть больше 0", None, form_data)

    # Parse datetime
    parsed_created_at = None
    if created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at)
        except ValueError:
            return render_form_error(request, "Некорректная дата", None, form_data)

    # Create message text
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
                request, "Ошибка сохранения в базу данных", None, form_data
            )

    set_flash_message(request, "Расход успешно добавлен", "success")
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)


@router.get("/{cost_id}/edit", response_class=HTMLResponse)
async def edit_cost_form(request: Request, cost_id: int):
    """Show edit cost form."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    async with get_db_session() as session:
        message = await get_message_by_id(session, cost_id)
        if not message:
            raise HTTPException(status_code=404, detail="Расход не найден")

        cost = parse_message_to_cost(message)

    return templates.TemplateResponse(
        request,
        "costs/form.html",
        {
            "cost": cost,
            "authenticated": True,
            "csrf_token": get_csrf_token(request),
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
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    # Validate CSRF token
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    form_data = {
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "created_at": created_at,
    }

    # Validate amount
    try:
        amount_decimal = Decimal(amount.replace(",", "."))
    except (InvalidOperation, ValueError):
        cost = await get_cost_for_error_response(cost_id)
        return render_form_error(request, "Некорректная сумма", cost, form_data)

    # Validate user_id
    if user_id < 1:
        cost = await get_cost_for_error_response(cost_id)
        return render_form_error(request, "User ID должен быть больше 0", cost, form_data)

    # Parse datetime
    parsed_created_at = None
    if created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at)
        except ValueError:
            cost = await get_cost_for_error_response(cost_id)
            return render_form_error(request, "Некорректная дата", cost, form_data)

    # Update message
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
            cost = await get_cost_for_error_response(cost_id)
            return render_form_error(
                request, "Ошибка сохранения в базу данных", cost, form_data
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
        return RedirectResponse(url=f"{settings.web_root_path}/costs/login", status_code=303)

    # Validate CSRF token
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
