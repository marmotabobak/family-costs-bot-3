# Tasks

## 1. Data model and migration

- [x] 1.1 Add `Currency` and `ExchangeRate` SQLAlchemy models in `bot/db/models.py` (fields per design), verified by importing the models and asserting `__tablename__`, columns, and constraints via a unit test.
- [x] 1.2 Add `amount` and `currency_id` columns to `Message` model (nullable), verified by unit test asserting the new columns and FK.
- [x] 1.3 Write Alembic migration that creates `currencies`, `exchange_rates`, adds the `messages` columns, and inserts `RUB` as the base currency (`is_base=true`, `default_rate=1`); verify by running `alembic upgrade head` against a fresh DB and asserting via `information_schema` that the tables/columns exist and the `RUB` row is present.
- [x] 1.4 Extend the same migration to backfill `messages.amount` and `messages.currency_id = RUB.id` by parsing existing `text` with a frozen copy of the current `rsplit`+`Decimal` logic, leaving rows with unparseable text as NULL/NULL; verify with an integration test that seeds mixed parseable and unparseable text rows before upgrade and asserts backfill results.
- [x] 1.5 Add partial unique index guaranteeing at most one row has `is_base=true`; verify by an integration test that attempts to insert two base currencies and expects an `IntegrityError`.
- [x] 1.6 Write the downgrade path (drops columns then tables); verify by running `alembic upgrade head && alembic downgrade -1` on a fresh DB and asserting the tables/columns are gone while original `messages.text` values remain.

## 2. Currency repository and rate-selection service

- [x] 2.1 Create `bot/db/repositories/currencies.py` with async CRUD for currencies (list, get by id, get by code, create, update, delete) and for dated exchange rates; verify with integration tests covering happy paths and unique-violation errors.
- [x] 2.2 Enforce base-currency invariants in the repository (first insert forces `is_base=true`; promotion demotes previous base in a single transaction; cannot delete base while other currencies exist; cannot delete a currency referenced by any `messages` row); verify with integration tests for each rule.
- [x] 2.3 Enforce validation rules (code matches `^[A-Z]{3}$`, `default_rate > 0`, dated `rate > 0`, unique `(currency_id, rate_date)`, cannot add dated rate for base currency); verify with unit and integration tests for each rule.
- [x] 2.4 Implement `bot/services/currency_rates.py` with `effective_rate(currency, date)` returning the greatest dated rate on-or-before `date` else `default_rate`, and `Decimal("1")` for base; verify with unit tests covering: exact-date match, only default, dated + default, multiple dated rates, date before all dated rates.
- [x] 2.5 Implement a per-request rate cache and `compute_base_amount(amount, currency, date)` helper; verify with a unit test asserting the underlying `effective_rate` is called once per `(currency, date)` across multiple invocations.

## 3. Bot input parsing and routing

- [x] 3.1 Extend `MESSAGE_RE` in `bot/services/message_parser.py` to accept optional trailing ` [<CUR>]` where `<CUR>` is exactly 3 uppercase letters, and add `currency_code: str | None` to the `Cost` dataclass; verify with unit tests covering: no brackets → None, `[USD]` → `"USD"`, `[usd]` → invalid line, `[USDD]` → invalid line, name-ending-in-uppercase like `foo BAR 10` → parses as name `foo BAR`.
- [x] 3.2 In the messages router, resolve `Cost.currency_code` against the catalogue: default to base when None, add the raw line to `invalid_lines` with an "unknown currency" reason when unknown; verify with an integration test posting a message with `[XYZ]` and asserting the row is not saved and the response mentions the unknown currency.
- [x] 3.3 Update `MessagesRepository.save` (and any other write paths) to write `amount` and `currency_id` on `messages`; verify with an integration test that saves a cost and asserts both columns are populated correctly for base and non-base cases.

## 4. Web UI configuration section

- [x] 4.1 Add an `admin_required` dependency wrapping the existing session/auth check; verify with an integration test asserting a non-admin session gets 403 on a protected route.
- [x] 4.2 Create `bot/web/config.py` router with routes for listing/creating/updating/deleting currencies, promoting a currency to base, and listing/creating/deleting dated exchange rates; mount it in `bot/web/app.py` under `admin_required`; verify with integration tests covering each endpoint's happy path and access denial.
- [x] 4.3 Create templates under `bot/web/templates/config/` (`currencies.html`, `rates.html`) and add a `Конфигурация` nav entry shown only for admins in `base.html`; verify by rendering both templates in an integration test and by asserting the nav item is absent for a non-admin session.
- [x] 4.4 Surface a clear error message when deletion is blocked by referring costs or by the "cannot delete base while others exist" rule; verify with an integration test asserting the error text appears in the rendered response.

## 5. Cost display: web and bot

- [x] 5.1 Update repositories that read costs (`get_user_costs_stats`, `get_user_recent_costs`, `get_user_costs_by_month`, `get_all_costs_paginated`, `get_all_users_costs_by_month`, and any others) to select `amount` and `currency_id` from columns instead of parsing `text`, and to aggregate base amounts (sum of `amount * effective_rate`); verify with integration tests seeding mixed-currency data and asserting totals in base currency.
- [x] 5.2 Update Web UI cost list templates to show a new "base amount" column with the base currency code adjacent to the amount column; verify with an integration test asserting both cells appear per row with expected values.
- [x] 5.3 Update Web UI cost create/edit forms to include a currency drop-down of catalogue currencies, base first, defaulting to base on create, and to reject unknown currencies on submit; verify with integration tests for the create, edit, and rejection flows.
- [x] 5.4 Introduce `format_cost_line(cost, base_currency, base_amount)` used everywhere the bot renders a cost line: base-currency → `<amount> <BASE_CODE>`; non-base → `<amount> <CUR_CODE> [<base_amount:.2> <BASE_CODE>]`; verify with unit tests for both branches including thousands formatting per existing convention.
- [x] 5.5 Wire `format_cost_line` into every bot rendering site (recent costs, monthly report, confirmation on save, etc.); verify with a targeted integration/e2e test for at least one non-base-currency round-trip through the bot.

## 6. End-to-end and cross-cutting verification

- [x] 6.1 Add e2e journey: admin creates `USD` with default rate `90`, adds a dated rate `95` for `2026-05-10`, adds a rate `97` for `2026-05-12`, then a user submits `lunch 10 [USD]` on `2026-05-13`; verify displayed base amount uses `97` and switches when the `2026-05-12` rate is edited to `100` (dynamic recompute).
- [x] 6.2 Add e2e journey: attempt to delete `USD` while a cost references it → 400/error; delete the cost → delete succeeds and cascades dated rates.
- [x] 6.3 Add e2e journey: attempt to delete or demote base `RUB` while another currency exists → error; promote another currency to base → previous base is demoted atomically.
- [x] 6.4 Add unit test for the migration's inline text-parser mirroring current behavior on a hand-crafted set of legacy `messages.text` values (`"coffee 250"`, `"a b c 12,50"`, `"malformed"`, `""`).
- [x] 6.5 Run `make lint` and `make test` and verify both pass without new warnings before considering the change ready for review.
