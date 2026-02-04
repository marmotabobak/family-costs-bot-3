"""Web UI for logs section (placeholder)."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings
from bot.web.auth import is_authenticated

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

# Setup templates
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path


@router.get("", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Show logs page (placeholder)."""
    if not is_authenticated(request):
        return RedirectResponse(url=f"{settings.web_root_path}/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "logs/index.html",
        {"authenticated": True},
    )
