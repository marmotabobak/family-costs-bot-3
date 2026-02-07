# Architect Agent Memory

## Project Architecture Overview

- **Auth:** `bot/web/auth.py` -- in-memory sessions dict, cookie-based, CSRF tokens, rate limiting
- **Users:** `bot/web/users.py` -- admin-only CRUD, uses `_require_admin()` guard
- **Costs:** `bot/web/costs.py` -- CRUD with role-based access (admins edit all, users edit own)
- **Logs:** `bot/web/logs.py` -- placeholder, admin-only
- **App:** `bot/web/app.py` -- FastAPI app, registers routers, import session handling
- **Config:** `bot/config.py` -- pydantic-settings, fields map to env vars automatically
- **Models:** `bot/db/models.py` -- User (id, telegram_id, name, role, created_at), Message
- **Repos:** `bot/db/repositories/users.py` -- CRUD functions, all take session + return without commit
- **Session cookie:** `costs_session`, 24h lifetime

## Migration Chain
`88c80207b946 -> 4c5c3f6f8088 -> 5820802edcb7 -> a1b2c3d4e5f6 -> b2c3d4e5f6a7 -> c3d4e5f6a7b8` (head)

## Test Structure
- `tests/unit/` -- mock-based, patch repos at module level
- `tests/e2e/test_admin_e2e.py` -- FakeDB stateful store, real auth sessions, comprehensive journeys
- `tests/integration/` -- needs real PostgreSQL (usually not run locally)
- E2E tests use `_patch_auth_settings` fixture, `_login()` helper returns CSRF token
- Pattern: `_setup_auth()` creates session directly in `auth_sessions` dict

## Key Design Patterns
- Auth context: `_get_auth_context(request)` returns dict with authenticated/user_name/is_admin
- Admin guard: `_require_admin(request)` returns RedirectResponse or None
- Form errors: `_render_form_error()` re-renders form with error + preserved form_data
- Flash messages: stored in session dict, consumed on next page load
- Templates extend `costs/base.html` which has nav, flash display
