"""Web UI for importing VkusVill checks."""

import json
import secrets
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

# Token storage: token -> {user_id, created_at, data}
# In production, use Redis or DB
import_sessions: dict[str, dict] = {}

app = FastAPI(title="Family Costs Bot - Import")


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "ok"}


# Setup templates and static files
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def generate_import_token(user_id: int) -> str:
    """Generate unique token for import session."""
    token = secrets.token_urlsafe(32)
    import_sessions[token] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "data": None,
    }
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

    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "token": token},
    )


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
            "upload.html",
            {"request": request, "token": token, "error": f"Ошибка чтения файла: {e}"},
        )

    # Validate structure
    if "checks" not in data:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "token": token, "error": "Неверный формат файла"},
        )

    # Store data in session
    session["data"] = data

    return RedirectResponse(url=f"/import/{token}/select", status_code=303)


@app.get("/import/{token}/select", response_class=HTMLResponse)
async def select_page(request: Request, token: str):
    """Show check selection page."""
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    if not session.get("data"):
        return RedirectResponse(url=f"/import/{token}")

    checks = session["data"]["checks"]

    # Parse dates for display
    for check in checks:
        dt = datetime.fromisoformat(check["date"])
        check["date_formatted"] = dt.strftime("%d.%m.%Y %H:%M")

    return templates.TemplateResponse(
        "select.html",
        {"request": request, "token": token, "checks": checks},
    )


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
        except SQLAlchemyError:
            await db_session.rollback()
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
                    "error": "Ошибка сохранения в базу данных. Попробуйте ещё раз.",
                },
            )

    saved_count = len(items_to_save)
    total_amount = sum(item["amount"] for item in items_to_save)

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
