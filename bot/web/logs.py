"""Web UI for logs section (placeholder)."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings
from bot.web.auth import get_current_user_name, is_admin, is_authenticated

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

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


def _require_admin(request: Request) -> RedirectResponse | None:
    """Check if user is admin, return redirect if not."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)
    if not is_admin(request):
        return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=303)
    return None


@router.get("", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Show logs page (placeholder). Admin only."""
    redirect = _require_admin(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        request,
        "logs/index.html",
        _get_auth_context(request),
    )
