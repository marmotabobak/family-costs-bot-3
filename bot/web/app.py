"""Web UI for importing VkusVill checks."""

import json
import logging
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from bot.config import Environment, settings
from bot.db.dependencies import get_session as get_db_session
from bot.db.repositories.messages import save_message
from bot.web.auth import router as auth_router
from bot.web.costs import router as costs_router
from bot.web.logs import router as logs_router
from bot.web.users import router as users_router

logger = logging.getLogger(__name__)

# Token storage: token -> {user_id, created_at, data}
# In production, use Redis or DB
import_sessions: dict[str, dict] = {}

app = FastAPI(title="Family Costs Bot - Web UI")

# Register routers
app.include_router(auth_router)
app.include_router(costs_router)
app.include_router(users_router)
app.include_router(logs_router)


@app.get("/")
async def root_redirect():
    """Redirect root to costs page (or login if not authenticated)."""
    return RedirectResponse(url=f"{settings.web_root_path}/costs", status_code=307)


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "ok"}


# Setup templates and static files
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["root_path"] = settings.web_root_path
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def generate_import_token(user_id: int) -> str:
    """Generate unique token for import session."""
    token = secrets.token_urlsafe(32)
    import_sessions[token] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "data": None,
    }
    logger.debug("Generated import token for user %s", user_id)
    return token


def get_session(token: str) -> dict | None:
    """Get import session by token."""
    return import_sessions.get(token)


# Dev-only route: only registered in non-prod environments
if settings.env != Environment.prod:

    @app.get("/dev/create-token/{user_id}")
    async def dev_create_token(user_id: int):
        """DEV ONLY: Create import token for testing."""
        token = generate_import_token(user_id)
        return {"token": token, "url": f"/import/{token}"}


@app.get("/import/{token}", response_class=HTMLResponse)
async def upload_page(request: Request, token: str):
    """Show upload form."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    return templates.TemplateResponse(request, "upload.html", {"token": token})


@app.post("/import/{token}/upload")
async def handle_upload(
    request: Request,
    token: str,
    file: Annotated[UploadFile, File()],
):
    """Handle JSON file upload."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    # Read and parse JSON
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return templates.TemplateResponse(
            request, "upload.html", {"token": token, "error": f"Ошибка чтения файла: {e}"}
        )

    # Validate structure
    if "checks" not in data:
        return templates.TemplateResponse(request, "upload.html", {"token": token, "error": "Неверный формат файла"})

    # Store data in session
    session["data"] = data

    return RedirectResponse(url=f"{settings.web_root_path}/import/{token}/select", status_code=303)


@app.get("/import/{token}/select", response_class=HTMLResponse)
async def select_page(request: Request, token: str):
    """Show check selection page."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    if not session.get("data"):
        return RedirectResponse(url=f"{settings.web_root_path}/import/{token}")

    checks = session["data"]["checks"]

    # Parse dates for display
    for check in checks:
        dt = datetime.fromisoformat(check["date"])
        check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")

    return templates.TemplateResponse(request, "select.html", {"token": token, "checks": checks})


@app.post("/import/{token}/save")
async def save_selected(
    request: Request,
    token: str,
):
    """Save selected items to database."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    form = await request.form()
    selected_items = form.getlist("items")

    if not selected_items:
        checks = session["data"]["checks"]
        for check in checks:
            dt = datetime.fromisoformat(check["date"])
            check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")
        return templates.TemplateResponse(
            request,
            "select.html",
            {"token": token, "checks": checks, "error": "Выберите хотя бы один товар"},
        )

    # Parse selected items: "check_idx:item_idx"
    items_to_save = []
    checks = session["data"]["checks"]

    for item_key in selected_items:
        if isinstance(item_key, str):
            check_idx, item_idx = map(int, item_key.split(":"))
            check = checks[check_idx]
            item = check["items"][item_idx]
            items_to_save.append(
                {
                    "name": item["name"],
                    "amount": item["sum"],
                    "date": datetime.fromisoformat(check["date"]),
                    "source": "vkusvill",
                    "store": check["store"],
                }
            )

    # Save to database
    async with get_db_session() as db_session:
        try:
            for item in items_to_save:
                await save_message(
                    session=db_session,
                    user_id=session["user_id"],
                    text=f"{item['name']} {item['amount']}",
                    created_at=item["date"],
                )
            await db_session.commit()
            logger.debug("Saved %d items for user %s via web import", len(items_to_save), session["user_id"])
        except SQLAlchemyError:
            logger.exception("DB error during web import for user %s", session["user_id"])
            await db_session.rollback()
            checks = session["data"]["checks"]
            for check in checks:
                dt = datetime.fromisoformat(check["date"])
                check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")
            return templates.TemplateResponse(
                request,
                "select.html",
                {
                    "token": token,
                    "checks": checks,
                    "error": "Ошибка сохранения в базу данных. Попробуйте ещё раз.",
                },
            )

    saved_count = len(items_to_save)
    total_amount = sum(item["amount"] for item in items_to_save)

    # Clear session data
    session["data"] = None

    return templates.TemplateResponse(
        request,
        "success.html",
        {"token": token, "saved_count": saved_count, "total_amount": total_amount},
    )


# In dev there is no reverse proxy to strip WEB_ROOT_PATH — mount the app under
# that prefix directly so /bot/costs etc. work out of the box.
# Guard against pytest: during tests ENV may still read as "dev" because Settings()
# is instantiated before pytest_configure sets ENV=test.
if settings.web_root_path and settings.env == Environment.dev and "pytest" not in sys.modules:
    from starlette.applications import Starlette
    from starlette.routing import Mount

    _inner = app
    app = Starlette(routes=[Mount(settings.web_root_path, app=_inner)])  # type: ignore[assignment]
