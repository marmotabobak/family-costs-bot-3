import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bot.config import Environment, settings
from bot.web.auth import router as auth_router
from bot.web.config import router as config_router
from bot.web.costs import router as costs_router
from bot.web.logs import router as logs_router
from bot.web.profile import router as profile_router
from bot.web.users import router as users_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Family Costs Bot - Web UI")

# Register routers
app.include_router(auth_router)
app.include_router(costs_router)
app.include_router(users_router)
app.include_router(profile_router)
app.include_router(logs_router)
app.include_router(config_router)


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


# In dev there is no reverse proxy to strip WEB_ROOT_PATH — mount the app under
# that prefix directly so /bot/costs etc. work out of the box.
# Guard against pytest: during tests ENV may still read as "dev" because Settings()
# is instantiated before pytest_configure sets ENV=test.
if settings.web_root_path and settings.env == Environment.dev and "pytest" not in sys.modules:
    from starlette.applications import Starlette
    from starlette.routing import Mount

    _inner = app
    app = Starlette(routes=[Mount(settings.web_root_path, app=_inner)])  # type: ignore[assignment]
