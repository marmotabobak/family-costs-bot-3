# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development setup
make install-dev      # Install all dependencies (prod + dev)
make hooks            # Install pre-commit hooks

# Running locally
make db               # Start only PostgreSQL container
make bot              # Run Telegram bot locally (no Docker)
make web              # Run web UI locally (uvicorn --reload, port 8000)

# Docker
make up               # Start all services (postgres + bot + web)
make down             # Stop all containers
make logs-bot         # Follow bot logs

# Database
make migrate          # Apply Alembic migrations (alembic upgrade head)

# Code quality
make lint             # ruff --fix + mypy
make pre-commit       # Run pre-commit on all files

# Testing
make test             # pytest -vv (all tests)
make test-cov         # pytest with coverage (html + xml reports)
```

Run a single test file: `pytest tests/unit/test_message_parser.py -vv`

Integration tests require a running PostgreSQL instance. Use `make db` first, then run `make migrate` (migrates the app database). The test suite automatically connects to a separate `<db>_test` database — it is created and migrated by the root `conftest.py` at the start of each test run, so no extra steps are needed. Production data is never touched by tests.

## Architecture

A family expense tracking system with two entry points that share the same PostgreSQL database:

1. **Telegram Bot** (`bot/main.py`, `bot/routers/`) — aiogram 3.x async bot. Users send plain text messages like `"coffee 250"` which are parsed into expense records.

2. **Web UI** (`bot/web/`) — FastAPI + Jinja2 admin panel for browsing/editing expenses, managing users, and importing VkusVill receipts.

### Request flow (bot)

```
Telegram message → Middleware (access control via users table)
  → messages.py router → message_parser.py (regex parse → Cost dataclass)
  → Validate → MessagesRepository.save() → DB
```

### Key layers

- **`bot/db/models.py`** — Two SQLAlchemy models: `Message` (expense record) and `User` (access control with role + bcrypt password for web login).
- **`bot/db/repositories/`** — All DB access goes through `MessagesRepository` and `UsersRepository` (async SQLAlchemy 2.x).
- **`bot/services/message_parser.py`** — Core parsing logic; regex-based, returns `Cost` dataclass.
- **`bot/middleware.py`** — aiogram middleware that gates all bot interactions on the `users` table.
- **`bot/web/auth.py`** — Session-based auth (24h sessions) with CSRF protection; separate from Telegram identity.
- **`bot/web/app.py`** — Mounts all web routers; also hosts the `/import/{token}` flow for VkusVill receipt import triggered from the bot.

### Configuration

`bot/config.py` uses pydantic-settings. Required env vars: `BOT_TOKEN`, `DATABASE_URL`. Optional: `ENV`, `ADMIN_TELEGRAM_ID`, `WEB_PASSWORD`, `WEB_ROOT_PATH`, `WEB_BASE_URL`.

### Test structure

```
tests/
  unit/          # ~300 tests, no external dependencies
  integration/   # ~130 tests, require PostgreSQL
  e2e/           # ~40 journey tests
```

CI runs on Python 3.11 and 3.12. Lint (ruff + mypy) is a prerequisite for the test job. Deploy to production triggers automatically on master merge via SSH.
