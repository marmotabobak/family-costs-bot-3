"""Web UI for importing VkusVill checks."""

import json
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from bot.config import Environment, settings
from bot.logging_config import setup_logging

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Token storage: token -> {user_id, created_at, data}
# In production, use Redis or DB
import_sessions: dict[str, dict] = {}

app = FastAPI(title="Family Costs Bot - Import")


# Request logging middleware for DEV mode
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and settings.env == Environment.dev:
            method = scope["method"]
            path = scope["path"]
            logger.debug("Request: %s %s", method, path)
        return await super().__call__(scope, receive, send)


if settings.env == Environment.dev:
    app.add_middleware(RequestLoggingMiddleware)

# Setup templates and static files
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/family-costs-bot/import/vkusvill/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def generate_import_token(user_id: int) -> str:
    """Generate unique token for import session."""
    token = secrets.token_urlsafe(32)
    import_sessions[token] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "data": None,
    }
    logger.debug("Generated import token for user_id=%d, token=%s", user_id, token)
    return token


def get_session(token: str) -> dict | None:
    """Get import session by token."""
    return import_sessions.get(token)


# Dev-only route: only registered in non-prod environments
if settings.env != Environment.prod:

    @app.get("/family-costs-bot/import/vkusvill/dev/create-token/{user_id}")
    async def dev_create_token(user_id: int):
        """DEV ONLY: Create import token for testing."""
        token = generate_import_token(user_id)
        return {"token": token, "url": f"/family-costs-bot/import/vkusvill/{token}"}


@app.get("/family-costs-bot/import/vkusvill/{token}", response_class=HTMLResponse)
async def upload_page(request: Request, token: str):
    """Show upload form."""
    logger.debug("Upload page requested: token=%s", token)
    session = get_session(token)
    if not session:
        logger.warning("Invalid token requested: %s", token)
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    logger.debug("Upload page rendered for user_id=%d", session["user_id"])
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "token": token},
    )


@app.post("/family-costs-bot/import/vkusvill/{token}/upload")
async def handle_upload(
    request: Request,
    token: str,
    file: Annotated[UploadFile, File()],
):
    """Handle JSON file upload."""
    logger.debug("File upload requested: token=%s, filename=%s", token, file.filename)
    session = get_session(token)
    if not session:
        logger.warning("Invalid token for upload: %s", token)
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    # Read and parse JSON
    try:
        content = await file.read()
        logger.debug("File read: size=%d bytes", len(content))
        data = json.loads(content.decode("utf-8"))
        logger.debug("JSON parsed successfully: checks_count=%d", len(data.get("checks", [])))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("File parsing error: token=%s, error=%s", token, e)
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "token": token, "error": f"Ошибка чтения файла: {e}"},
        )

    # Validate structure
    if "checks" not in data:
        logger.warning("Invalid file format: token=%s, missing 'checks' key", token)
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "token": token, "error": "Неверный формат файла"},
        )

    # Store data in session
    session["data"] = data
    logger.info("File uploaded successfully: user_id=%d, checks_count=%d", session["user_id"], len(data["checks"]))

    return RedirectResponse(url=f"/family-costs-bot/import/vkusvill/{token}/select", status_code=303)


@app.get("/family-costs-bot/import/vkusvill/{token}/select", response_class=HTMLResponse)
async def select_page(request: Request, token: str):
    """Show check selection page."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    if not session.get("data"):
        return RedirectResponse(url=f"/family-costs-bot/import/vkusvill/{token}")

    checks = session["data"]["checks"]

    # Parse dates for display
    for check in checks:
        dt = datetime.fromisoformat(check["date"])
        check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")

    return templates.TemplateResponse(
        "select.html",
        {"request": request, "token": token, "checks": checks},
    )


@app.post("/family-costs-bot/import/vkusvill/{token}/save")
async def save_selected(
    request: Request,
    token: str,
):
    """Save selected items to database."""
    logger.debug("Save selected requested: token=%s", token)
    session = get_session(token)
    if not session:
        logger.warning("Invalid token for save: %s", token)
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    form = await request.form()
    selected_items = form.getlist("items")
    logger.debug("Selected items count: %d", len(selected_items))

    if not selected_items:
        if not session.get("data"):
            return RedirectResponse(url=f"/family-costs-bot/import/vkusvill/{token}")
        checks = session["data"]["checks"]
        for check in checks:
            dt = datetime.fromisoformat(check["date"])
            check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")
        return templates.TemplateResponse(
            "select.html",
            {
                "request": request,
                "token": token,
                "checks": checks,
                "error": "Выберите хотя бы один товар",
            },
        )

    # Parse selected items: "check_idx:item_idx"
    items_to_save = []
    checks = session["data"]["checks"]

    for item_key in selected_items:
        if isinstance(item_key, str):
            check_idx, item_idx = map(int, item_key.split(":"))
            check = checks[check_idx]
            item = check["items"][item_idx]
            items_to_save.append({
                "name": item["name"],
                "amount": item["sum"],
                "date": datetime.fromisoformat(check["date"]),
                "source": "vkusvill",
                "store": check["store"],
            })

    # TODO: Save to database using session["user_id"]
    saved_count = len(items_to_save)
    total_amount = sum(item["amount"] for item in items_to_save)
    logger.info(
        "Items saved: user_id=%d, count=%d, total_amount=%.2f",
        session["user_id"],
        saved_count,
        total_amount,
    )

    # Clear session data
    session["data"] = None

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "token": token,
            "saved_count": saved_count,
            "total_amount": total_amount,
        },
    )
