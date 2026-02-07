"""Shared authentication for the admin panel."""

import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import Environment, settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.users import get_all_users, get_user_by_telegram_id
from bot.security import verify_password

logger = logging.getLogger(__name__)

router = APIRouter()

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path

# In-memory session storage
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
        del auth_sessions[token]
        return None

    return session


def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated."""
    session = get_session_from_cookie(request)
    return session is not None and session.get("authenticated", False)


def get_current_user_telegram_id(request: Request) -> int | None:
    """Get current user's telegram_id from session."""
    session = get_session_from_cookie(request)
    if session:
        return session.get("telegram_id")
    return None


def get_current_user_role(request: Request) -> str | None:
    """Get current user's role from session."""
    session = get_session_from_cookie(request)
    if session:
        return session.get("role")
    return None


def get_current_user_name(request: Request) -> str | None:
    """Get current user's name from session."""
    session = get_session_from_cookie(request)
    if session:
        return session.get("user_name")
    return None


def get_current_user_id(request: Request) -> int | None:
    """Get current user's DB id from session."""
    session = get_session_from_cookie(request)
    if session:
        return session.get("user_id")
    return None


def is_admin(request: Request) -> bool:
    """Check if current user is admin."""
    return get_current_user_role(request) == "admin"


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


# --- Auth routes ---


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login form."""
    cleanup_expired_sessions()
    cleanup_old_rate_limits()

    if is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)

    # Fetch users for dropdown
    async with get_db_session() as session:
        users = await get_all_users(session)

    return templates.TemplateResponse(
        request, "costs/login.html", {"authenticated": False, "users": users}
    )


@router.post("/login")
async def login(request: Request, password: str = Form(...), user_id: str = Form(...)):
    """Handle login form submission."""
    client_ip = request.client.host if request.client else "unknown"

    # Fetch users for error responses
    async with get_db_session() as session:
        users = await get_all_users(session)

    if not check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {
                "error": "Слишком много попыток входа. Повторите через 5 минут.",
                "authenticated": False,
                "users": users,
            },
        )

    # Validate user selection
    if not user_id:
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {"error": "Выберите пользователя", "authenticated": False, "users": users},
        )

    try:
        telegram_id = int(user_id)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "costs/login.html",
            {"error": "Некорректный пользователь", "authenticated": False, "users": users},
        )

    # Get user from DB
    async with get_db_session() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if not user:
            return templates.TemplateResponse(
                request,
                "costs/login.html",
                {"error": "Пользователь не найден", "authenticated": False, "users": users},
            )

        # Check if user has a password set
        if not user.password_hash:
            return templates.TemplateResponse(
                request,
                "costs/login.html",
                {
                    "error": "Пароль для этого пользователя не установлен. Обратитесь к администратору.",
                    "authenticated": False,
                    "users": users,
                },
            )

        # Verify password
        if not verify_password(password, str(user.password_hash)):
            record_login_attempt(client_ip)
            return templates.TemplateResponse(
                request,
                "costs/login.html",
                {"error": "Неверный пароль", "authenticated": False, "users": users},
            )

        # Auto-promote to admin if telegram_id matches ADMIN_TELEGRAM_ID
        if (
            settings.admin_telegram_id
            and user.telegram_id == settings.admin_telegram_id
            and user.role != "admin"
        ):
            user.role = "admin"  # type: ignore[assignment]
            await session.commit()
            logger.info("Auto-promoted user %s to admin (ADMIN_TELEGRAM_ID match)", user.name)

    # Create session with user info
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    auth_sessions[token] = {
        "authenticated": True,
        "created_at": datetime.now(),
        "csrf_token": csrf_token,
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "user_name": user.name,
        "role": user.role,
    }

    response = RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_LIFETIME,
        secure=settings.env == Environment.prod,
    )
    logger.info("User %s (role=%s) logged in to admin panel", user.name, user.role)
    return response


@router.get("/logout")
async def logout(request: Request):
    """Handle logout."""
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in auth_sessions:
        del auth_sessions[token]

    response = RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE)
    return response
