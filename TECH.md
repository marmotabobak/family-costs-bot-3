# Technical Reference

Architecture, data flows, patterns, and internals of Family Costs Bot.

---

## System Overview

Two independent entry points share one PostgreSQL database:

```
Telegram ──► Bot (aiogram)  ─┐
                              ├─► PostgreSQL
Browser ──► Web (FastAPI)   ─┘
```

Both run as separate Docker containers (`bot`, `web`) with a shared `postgres` container. Neither knows about the other's internal state — they coordinate only through the database.

---

## Bot Architecture

### Startup (`bot/main.py`)

```
main()
  └─ create Bot(token, parse_mode=HTML)
  └─ create Dispatcher
  └─ register AllowedUsersMiddleware
  └─ include routers: messages → menu → import_cmd → common
  └─ set bot commands (/menu, /import, /help)
  └─ register SIGTERM/SIGINT handlers
  └─ dp.start_polling(bot)
```

Middleware is registered on the dispatcher's `message` observer, not globally, so it only fires for `Message` events — callbacks pass through unchecked.

### Routers

| Router | File | Handles |
|--------|------|---------|
| `messages` | `routers/messages.py` | Plain text messages → parse → save |
| `menu` | `routers/menu.py` | `/menu` + all `InlineKeyboardButton` callbacks |
| `import_cmd` | `routers/import_cmd.py` | `/import` → generate token → send URL |
| `common` | `routers/common.py` | `/start`, `/help` |

Router order matters in aiogram: the first matching handler wins. `messages` router catches all text, so it must be registered before `common` (which also has text handlers for commands).

### Message Handling Flow

```
User sends text
  │
  ▼
AllowedUsersMiddleware
  ├─ get_all_telegram_ids() from DB
  ├─ if table empty → allow all (initial setup)
  ├─ if user not in list → answer(MSG_ACCESS_DENIED) + return
  └─ else → call handler
         │
         ▼
  handle_message() [routers/messages.py]
    ├─ guard: no text or no from_user → return
    ├─ parse_message(text) [services/message_parser.py]
    │    ├─ MessageMaxLengthExceed → answer(MSG_MESSAGE_MAX_LENGTH)
    │    ├─ MessageMaxLinesCountExceed → answer(MSG_MESSAGE_MAX_LINES_COUNT)
    │    └─ MessageMaxLineLengthExceed → answer(MSG_MESSAGE_MAX_LINE_LENGTH)
    │
    ├─ all lines invalid → answer(MSG_PARSE_ERROR) + answer(HELP_TEXT)
    ├─ some lines invalid → FSM: set state=waiting_confirmation
    │                            store valid_costs in state
    │                            answer(confirmation_message + keyboard)
    └─ all lines valid → save_message() → answer(success_message)
```

### FSM (Finite State Machine)

Used only in the confirmation flow (`SaveCostsStates.waiting_confirmation`). State data:

```python
{"valid_costs": [Cost(name, amount), ...]}
```

On `CALLBACK_CONFIRM`: retrieve state data → save → clear state → edit message.
On `CALLBACK_CANCEL`: clear state → edit message.

aiogram's built-in `MemoryStorage` is used (no Redis). State is lost on bot restart.

### Message Parser (`services/message_parser.py`)

```python
COST_PATTERN = re.compile(
    r"^\s*(?P<text>.+?)\s+(?P<amount>[+-]?\d+(?:[.,]\d+)?)\s*$"
)
```

- Strips leading/trailing whitespace per line
- Skips empty lines
- Converts `,` → `.` in amounts before `Decimal()`
- Returns `ParseResult(valid: list[Cost], invalid: list[str])`

Raises custom exceptions (`bot/exceptions.py`) for hard limits before parsing begins.

---

## Web Architecture

### FastAPI App (`web/app.py`)

```python
app = FastAPI(root_path=settings.web_root_path)
app.include_router(auth_router)
app.include_router(costs_router)
app.include_router(users_router)
app.include_router(profile_router)
app.include_router(logs_router)
# import token routes registered directly on app
```

`root_path` handles nginx reverse-proxy prefix (`WEB_ROOT_PATH=/bot`): all generated URLs in templates automatically include the prefix.

### Authentication (`web/auth.py`)

Session-based, not JWT. Flow:

```
POST /login
  ├─ check rate limit (5 attempts / 5 min per IP, in-memory counter)
  ├─ verify password against settings.web_password (plain comparison)
  │   or against user.password_hash (bcrypt) if user exists in DB
  ├─ create session: uuid4 token → stored in server-side dict
  │   {token: {"user_id": id, "expires": now+24h}}
  └─ set SESSION_COOKIE=token (httponly, secure in prod)
```

Sessions are stored in a module-level dict (`_sessions: dict[str, SessionData]`). No persistence — sessions reset on restart.

CSRF: each form includes a hidden `csrf_token` field. The token is stored in the session and verified on every state-changing request.

### Role-based Access

```python
# Dependency injected into route handlers
async def get_current_user(request: Request) -> User: ...
async def require_admin(user: User = Depends(get_current_user)) -> User: ...
```

Admin routes (`/users`, `/logs`) use `require_admin`. Regular authenticated routes use `get_current_user`. The `/costs` list shows all users' records; edit/delete is restricted to own records for non-admins.

### VkusVill Import Flow

Token-based, no session required (designed for mobile use):

```
Bot: /import
  └─ generate uuid4 token
  └─ store {token: user_id} in memory (web/app.py module level)
  └─ send URL: {WEB_BASE_URL}/import/{token}

Web:
  GET /import/{token}         → upload form
  POST /import/{token}/upload → parse JSON, store items in token session
  GET /import/{token}/select  → show parsed items with checkboxes
  POST /import/{token}/save   → save selected items, invalidate token
```

Tokens are single-use and kept only in memory. The `GET /dev/create-token/{user_id}` endpoint is available only when `ENV=dev`.

---

## Database

### Models (`bot/db/models.py`)

**`messages` table:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | auto-increment |
| `user_id` | BigInteger | FK-style (no FK constraint), indexed, > 0 |
| `text` | Text | raw expense string, e.g. `"Продукты 100"` |
| `created_at` | DateTime | server default: `now()` |

**`users` table:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | auto-increment |
| `telegram_id` | BigInteger | unique, indexed |
| `name` | String(255) | display name |
| `role` | String(20) | `"user"` or `"admin"`, default `"user"` |
| `password_hash` | String(255) | nullable, bcrypt hash |
| `created_at` | DateTime | server default: `now()` |

No foreign key between `messages.user_id` and `users.telegram_id` — decoupled intentionally to allow messages before user exists.

### Migrations (Alembic)

7 migration versions, applied sequentially:

1. Create `messages` table
2. Create `users` table
3. Add `role` to `users`
4. Widen `messages.user_id` to BigInteger
5. Add index on `messages.user_id`
6. Add check constraint: `messages.user_id > 0`
7. Add `password_hash` to `users`

The `bot` container runs `alembic upgrade head` before starting polling.

### Repository Pattern

All DB access goes through repository functions, not inline queries:

```
bot/db/repositories/
├── messages.py   # ~30 functions
└── users.py      # ~10 functions
```

Key message functions:

- `save_message(session, user_id, text)` — insert, no commit (caller commits)
- `get_user_costs_by_month(session, user_id, year, month)` → `list[tuple[str, Decimal, datetime]]`
- `get_user_available_months(session, user_id)` → `list[tuple[int, int]]`
- `delete_messages_by_ids(session, ids, user_id)` — filters by user_id for isolation
- `get_all_costs_paginated(session, page, page_size, filters, order_by)` — web list
- `bulk_delete_messages`, `bulk_update_messages_date`, `bulk_update_messages_user`

### Session Management

```python
# bot/db/dependencies.py
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

Each request/handler gets its own session. Commits are explicit — `save_message()` inserts without committing so the caller can batch multiple inserts.

---

## Configuration (`bot/config.py`)

Pydantic Settings with validation:

```python
class Settings(BaseSettings):
    bot_token: str          # validated: len >= 20, contains ":"
    database_url: str       # validated: starts with "postgresql"
    env: Environment        # dev | test | prod
    admin_telegram_id: int | None
    admin_default_password: str
    web_base_url: str
    web_password: str
    web_root_path: str

    @property
    def debug(self) -> bool:
        return self.env in (Environment.dev, Environment.test)
```

Loaded from environment variables + `.env` file. Validated at import time — missing required vars crash startup with a clear error.

---

## Security

### Bot Access Control

`AllowedUsersMiddleware` fires on every `Message`. It:
1. Skips non-`Message` events (callbacks, etc.)
2. Skips messages without `from_user`
3. Loads all `telegram_id`s from `users` table
4. If table is empty → allows all (initial setup mode)
5. If user not in list → `message.answer(MSG_ACCESS_DENIED)` + `return`
6. On DB error → allows all (graceful degradation, logs warning)

### Web Security

- **CSRF**: token per session, verified on all POST/PUT/DELETE
- **Rate limiting**: login endpoint — 5 attempts per 5 minutes per IP (in-memory, resets on restart)
- **Password storage**: bcrypt via `passlib` (`bot/security.py`)
- **Session cookie**: `httponly=True`, `secure=True` in prod
- **Admin isolation**: non-admin users cannot access `/users` or `/logs`
- **Data isolation**: `delete_messages_by_ids` always includes `user_id` filter

### HTML Escaping

All user-supplied strings rendered in bot HTML messages go through:

```python
def esc(text: str) -> str:
    return html.escape(text, quote=False)
```

`quote=False` keeps `"` unescaped (not needed in HTML body context). `<`, `>`, `&` are escaped. This prevents `ParseMode.HTML` from interpreting user input as markup.

---

## Utilities

### `format_amount(amount, sep)` (`bot/utils.py`)

```python
format_amount(Decimal("1234.56"), sep="_")  # → "1_234.56"
format_amount(Decimal("1000"), sep="_")      # → "1_000"   (omits .00)
format_amount(Decimal("-500"), sep=" ") # → "-500"
```

Bot uses `sep="_"`, web uses `sep=" "` (non-breaking space).

### `pluralize(n, form1, form2, form5)` (`bot/utils.py`)

Russian noun pluralization:
- 1 → form1 (`расход`)
- 2–4 → form2 (`расхода`)
- 5+ → form5 (`расходов`)

---

## Testing Strategy

### Structure

```
tests/
├── conftest.py          # env guard (blocks test on ENV=prod)
├── unit/
│   ├── conftest.py      # shared fixtures: mock_message, mock_state, mock_session
│   └── test_*.py        # 19 files, ~408 tests
├── integration/
│   ├── conftest.py      # real DB session, cleanup_db autouse fixture
│   └── test_*.py        # ~116 tests
└── e2e/
    └── test_admin_e2e.py  # ~108 tests via httpx TestClient
```

### Unit Test Patterns

Async handlers are tested with `@pytest.mark.asyncio` (auto mode via `asyncio_mode = "auto"` in pyproject.toml).

DB calls are mocked at the import path of the module under test:
```python
with patch("bot.routers.messages.get_session") as mock_get_session:
    mock_get_session.return_value.__aenter__.return_value = mock_session
```

Aiogram types (`Message`, `User`, `CallbackQuery`) use `MagicMock(spec=T)` with manually set attributes. `AsyncMock` for coroutine attributes (`message.answer`, `state.set_state`).

### Integration Test Patterns

Real PostgreSQL, isolated per test:

```python
@pytest.fixture(autouse=True)
async def cleanup_db(session):
    await session.execute(delete(Message))
    await session.commit()
    yield
```

Tests skip automatically if PostgreSQL is unreachable (connection check in `conftest.py`).

### E2E Test Patterns

FastAPI `TestClient` via httpx — synchronous HTTP requests against the actual app. Tests the full stack including CSRF, sessions, redirects, and HTML responses.

---

## Logging

Configured in `bot/logging_config.py`:

- `ENV=dev` / `ENV=test`: `DEBUG` level, SQLAlchemy echo enabled
- `ENV=prod`: `INFO` level, no SQL logging

Structured as plain text to stdout (Docker captures it). No file rotation or external log aggregation currently.

---

## Graceful Shutdown

```python
# bot/main.py
async def shutdown(signal_name: str) -> None:
    logger.info(f"Received {signal_name}, shutting down...")
    await dp.stop_polling()
    await bot.session.close()
    await engine.dispose()
```

Signal handlers registered for `SIGTERM` (Docker stop) and `SIGINT` (Ctrl+C). Ensures:
- In-flight updates are processed before exit
- DB connection pool is released cleanly
- No zombie connections in PostgreSQL

---

## Deployment

Production stack on a single Linux host:

```
nginx (reverse proxy)
  ├─ /          → static / other
  └─ /bot/      → FastAPI:8000 (strips /bot prefix via proxy_pass)

docker-compose
  ├─ postgres:5432
  ├─ bot (polling, no exposed port)
  └─ web:8000
```

`WEB_ROOT_PATH=/bot` tells FastAPI its root path so it generates correct URLs in responses.

Deploy script (triggered by GitHub Actions on master merge):
1. SSH into server
2. `git pull`
3. `docker-compose up -d --build`

The `bot` container runs `alembic upgrade head && python -m bot.main`, so migrations are applied automatically on each deploy.
